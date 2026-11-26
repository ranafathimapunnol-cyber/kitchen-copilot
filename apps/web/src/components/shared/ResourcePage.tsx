"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode, SubmitEvent } from "react";
import { usePathname } from "next/navigation";
import {
  Ban,
  Eye,
  Pencil,
  Plus,
  RefreshCw,
  SearchX,
  Trash2,
} from "lucide-react";

import { api } from "@/lib/api/client";
import {
  FETCH_PAGE_SIZE,
  MAX_FETCH_PAGES,
  fetchAllRecords,
} from "@/lib/api/list";
import { findNavEntry } from "@/lib/navigation";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import {
  Field,
  SelectInput,
  TextArea,
  TextInput,
} from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SearchSelect from "@/components/ui/SearchSelect";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import type { ColumnConfig, FieldConfig, ResourceConfig } from "@/types";

type RecordItem = Record<string, unknown>;

type Option = { value: string; label: string; active: boolean };

type StatusFilter = "all" | "active" | "inactive";

type PendingAction = { kind: "deactivate" | "delete"; record: RecordItem };

const PAGE_SIZES = [10, 25, 50];

/**
 * The permission module behind each master-data endpoint, mirroring
 * MASTER_RESOURCES in services/api/app/api/routes/master_data.py.
 *
 * Used only to hide controls the API would refuse. The API stays the
 * authority: create needs <module>.create, update and deactivate need
 * <module>.update, delete is ADMIN-only.
 */
const RESOURCE_MODULES: Record<string, "inventory" | "menu"> = {
  categories: "inventory",
  units: "inventory",
  "unit-conversions": "inventory",
  items: "inventory",
  suppliers: "inventory",
  "meal-sessions": "menu",
  menus: "menu",
  "menu-main-items": "menu",
};

function resourceModule(endpoint: string): "inventory" | "menu" | null {
  const key = endpoint.split("?")[0].split("/").filter(Boolean).pop() ?? "";
  return RESOURCE_MODULES[key] ?? null;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Loads select options for every field that names an optionsEndpoint.
 * Inactive rows are kept so existing records still show their names; the
 * form offers only active ones. A source the user cannot read leaves that
 * field's labels as raw IDs instead of failing the whole page.
 */
async function loadOptions(
  fields: FieldConfig[]
): Promise<Record<string, Option[]>> {
  const optionFields = fields.filter((field) => field.optionsEndpoint);
  const endpoints = [
    ...new Set(optionFields.map((field) => field.optionsEndpoint!)),
  ];

  const results = await Promise.allSettled(
    endpoints.map((endpoint) => fetchAllRecords(endpoint))
  );

  const rowsByEndpoint = new Map<string, RecordItem[]>();
  endpoints.forEach((endpoint, index) => {
    const result = results[index];
    if (result.status === "fulfilled") {
      rowsByEndpoint.set(endpoint, result.value.rows);
    }
  });

  return Object.fromEntries(
    optionFields.map((field) => {
      const rows = rowsByEndpoint.get(field.optionsEndpoint!) ?? [];

      return [
        field.name,
        rows.map((row) => ({
          value: String(row.id ?? row.value ?? ""),
          label: String(
            row[field.optionLabel || "name"] ??
              row.name ??
              row.title ??
              row.id ??
              ""
          ),
          active: row.is_active !== false,
        })),
      ];
    })
  );
}

/** "Categories" → "Category", "Unit Conversions" → "Unit Conversion". */
function singular(title: string): string {
  if (title.endsWith("ies")) return `${title.slice(0, -3)}y`;
  if (title.endsWith("s")) return title.slice(0, -1);
  return title;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function ResourcePage({
  config,
  rowAction,
}: {
  config: ResourceConfig;
  /** An extra per-row action (e.g. classifying an item), given a refresh callback. */
  rowAction?: (record: RecordItem, refresh: () => Promise<void>) => ReactNode;
}) {
  const pathname = usePathname();
  const nav = findNavEntry(pathname);
  const toast = useToast();
  const { role, permissions } = useAuthorization();

  const noun = singular(config.title);

  const [records, setRecords] = useState<RecordItem[]>([]);
  const [options, setOptions] = useState<Record<string, Option[]>>({});
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const [pending, setPending] = useState<PendingAction | null>(null);
  const [pendingBusy, setPendingBusy] = useState(false);

  // ---- Permissions: hide what the API would refuse ----------------------
  const permissionModule = resourceModule(config.endpoint);
  const isAdmin = role === "ADMIN";
  const allows = (action: "create" | "update") =>
    isAdmin ||
    (permissionModule !== null &&
      permissions.includes(`${permissionModule}.${action}`));

  const canCreate = allows("create");
  const canUpdate = allows("update");
  const canDelete = isAdmin;
  const showActions = canUpdate || canDelete || Boolean(rowAction);

  // ---- Data -------------------------------------------------------------
  // State is set only in promise callbacks, so this is safe in an effect.
  const fetchData = useCallback(() => {
    return Promise.all([
      fetchAllRecords(config.endpoint),
      loadOptions(config.fields),
    ])
      .then(([list, nextOptions]) => {
        setRecords(list.rows);
        setTruncated(list.truncated);
        setOptions(nextOptions);
        setLoadError("");
      })
      .catch((err: unknown) => {
        setLoadError(errorMessage(err, "Unable to load records."));
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, [config]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const refresh = () => {
    setRefreshing(true);
    return fetchData();
  };

  // ---- Display helpers ----------------------------------------------------
  const fieldFor = (name: string) =>
    config.fields.find((field) => field.name === name);

  const optionsFor = (field: FieldConfig | undefined): Option[] => {
    if (!field) return [];
    if (field.options) {
      return field.options.map((option) => ({ ...option, active: true }));
    }
    return options[field.name] ?? [];
  };

  const getColumnValue = (record: RecordItem, column: ColumnConfig) => {
    const fieldName = column.optionField || column.key;
    const rawValue = record[column.key];

    if (column.labels) {
      if (rawValue === null || rawValue === undefined || rawValue === "") {
        return column.emptyLabel ?? "—";
      }
      return column.labels[String(rawValue)] ?? displayValue(rawValue);
    }

    const match = optionsFor(fieldFor(fieldName)).find(
      (option) => option.value === String(rawValue ?? "")
    );

    return match?.label ?? displayValue(rawValue);
  };

  const isNumericColumn = (column: ColumnConfig) =>
    fieldFor(column.key)?.type === "number";

  const primaryColumn = config.columns.find((column) => column.key !== "id");

  const recordLabel = (record: RecordItem) => {
    const name = record.name ?? record.title;
    return typeof name === "string" && name.trim()
      ? name
      : `${noun} #${String(record.id ?? "")}`;
  };

  // ---- Search, filter, paginate -----------------------------------------
  const hasStatus = records.some(
    (record) => typeof record.is_active === "boolean"
  );
  const activeCount = records.filter((r) => r.is_active !== false).length;
  const inactiveCount = records.length - activeCount;

  const needle = query.trim().toLowerCase();

  const filtered = records.filter((record) => {
    if (status === "active" && record.is_active === false) return false;
    if (status === "inactive" && record.is_active !== false) return false;
    if (!needle) return true;

    return [String(record.id ?? ""), ...config.columns.map((c) => getColumnValue(record, c))]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filtered.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  const changeQuery = (value: string) => {
    setQuery(value);
    setPage(1);
  };

  const changeStatus = (value: StatusFilter) => {
    setStatus(value);
    setPage(1);
  };

  const clearFilters = () => {
    setQuery("");
    setStatus("all");
    setPage(1);
  };

  // ---- Create / edit ------------------------------------------------------
  const openCreate = () => {
    setEditingId(null);
    setForm({});
    setFormError("");
    setFormOpen(true);
  };

  const openEdit = (record: RecordItem) => {
    if (record.is_active === false) return;

    const nextForm: Record<string, string> = {};

    for (const field of config.fields) {
      const value = record[field.name];
      nextForm[field.name] =
        value === null || value === undefined ? "" : String(value);
    }

    setForm(nextForm);
    setEditingId(record.id as string | number);
    setFormError("");
    setFormOpen(true);
  };

  const closeForm = () => {
    if (!saving) setFormOpen(false);
  };

  const updateField = (name: string, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
  };

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    try {
      // Payload rules are unchanged from the previous ResourcePage.
      const payload: Record<string, unknown> = {};

      for (const field of config.fields) {
        const value = form[field.name]?.trim() ?? "";

        if (field.type === "number") {
          if (value === "" && field.required) {
            throw new Error(`${field.label} is required.`);
          }

          const numberValue = value === "" ? 0 : Number(value);

          if (!Number.isFinite(numberValue) || numberValue < 0) {
            throw new Error(
              `${field.label} must be a valid non-negative number.`
            );
          }

          payload[field.name] = numberValue;
        } else if (field.type === "select") {
          if (field.required && !value) {
            throw new Error(`Please select ${field.label.toLowerCase()}.`);
          }

          payload[field.name] = value ? Number(value) : null;
        } else {
          if (field.required && !value) {
            throw new Error(`${field.label} is required.`);
          }

          payload[field.name] = value || null;
        }
      }

      if (editingId !== null) {
        await api.put(
          `${config.endpoint}/${encodeURIComponent(String(editingId))}`,
          payload
        );
        toast.success(`${noun} updated.`);
      } else {
        await api.post(config.endpoint, payload);
        toast.success(`${noun} created.`);
        // Newest records come first, so a new one lands on page 1.
        setPage(1);
      }

      setFormOpen(false);
      setEditingId(null);
      setForm({});
      await refresh();
    } catch (err) {
      setFormError(errorMessage(err, "Unable to save record."));
    } finally {
      setSaving(false);
    }
  };

  // ---- Deactivate / delete -----------------------------------------------
  const confirmPending = async () => {
    if (!pending) return;

    const { kind, record } = pending;
    const id = encodeURIComponent(String(record.id));
    const label = recordLabel(record);

    setPendingBusy(true);
    setActionError("");

    try {
      const result =
        kind === "delete"
          ? await api.delete<{ message?: string }>(`${config.endpoint}/${id}`)
          : await api.post<{ message?: string }>(
              `${config.endpoint}/${id}/deactivate`,
              {}
            );

      toast.success(
        result?.message ||
          (kind === "delete" ? `${label} deleted.` : `${label} deactivated.`)
      );
      setPending(null);
      await refresh();
    } catch (err) {
      setPending(null);
      setActionError(
        errorMessage(
          err,
          kind === "delete"
            ? "Unable to delete record."
            : "Unable to deactivate record."
        )
      );
    } finally {
      setPendingBusy(false);
    }
  };

  // ---- Rendering pieces ---------------------------------------------------
  const renderCell = (record: RecordItem, column: ColumnConfig) => {
    const value = getColumnValue(record, column);

    if (column.key === "id") {
      return (
        <span className="font-mono text-xs text-slate-500">#{value}</span>
      );
    }

    if (column === primaryColumn) {
      return <span className="font-medium text-slate-900">{value}</span>;
    }

    if (value === "—") return <span className="text-slate-400">—</span>;

    return (
      <span className="block max-w-[18rem] truncate" title={value}>
        {value}
      </span>
    );
  };

  const renderActions = (record: RecordItem) => {
    const inactive = record.is_active === false;
    const hasId = record.id !== undefined && record.id !== null;
    const label = recordLabel(record);

    return (
      <div className="flex items-center justify-end gap-0.5">
        {rowAction?.(record, refresh)}

        {canUpdate && (
          <IconButton
            size="sm"
            tone="brand"
            icon={<Pencil size={15} />}
            label={
              inactive ? `${label} is inactive and can't be edited` : `Edit ${label}`
            }
            disabled={inactive || !hasId}
            onClick={() => openEdit(record)}
          />
        )}

        {canUpdate && hasStatus && !inactive && (
          <IconButton
            size="sm"
            tone="warning"
            icon={<Ban size={15} />}
            label={`Deactivate ${label}`}
            disabled={!hasId}
            onClick={() => setPending({ kind: "deactivate", record })}
          />
        )}

        {canDelete && (
          <IconButton
            size="sm"
            tone="danger"
            icon={<Trash2 size={15} />}
            label={`Delete ${label} permanently`}
            disabled={!hasId}
            onClick={() => setPending({ kind: "delete", record })}
          />
        )}
      </div>
    );
  };

  const statusBadge = (record: RecordItem) =>
    record.is_active === false ? (
      <Badge tone="neutral" dot>
        Inactive
      </Badge>
    ) : (
      <Badge tone="success" dot>
        Active
      </Badge>
    );

  const renderField = (field: FieldConfig, index: number) => {
    const value = form[field.name] ?? "";
    const wide = field.type === "textarea" || config.fields.length < 3;

    return (
      <Field
        key={field.name}
        label={field.label}
        required={field.required}
        className={wide ? "sm:col-span-2" : undefined}
      >
        {({ id, describedBy }) => {
          const common = {
            id,
            "aria-describedby": describedBy,
            required: field.required,
            "data-autofocus": index === 0 ? true : undefined,
          };

          if (field.type === "textarea") {
            return (
              <TextArea
                {...common}
                placeholder={field.placeholder}
                value={value}
                onChange={(event) => updateField(field.name, event.target.value)}
              />
            );
          }

          if (field.type === "select") {
            // Active options, plus the current value if it has since been
            // deactivated, so editing never silently blanks it.
            const choices = optionsFor(field).filter(
              (option) => option.active || option.value === value
            );

            if (field.searchable) {
              return (
                <SearchSelect
                  id={id}
                  aria-describedby={describedBy}
                  required={field.required}
                  data-autofocus={index === 0 ? true : undefined}
                  value={value}
                  noun={`${field.label.toLowerCase()}s`}
                  placeholder={`Select ${field.label.toLowerCase()}`}
                  options={choices.map((option) => ({
                    value: option.value,
                    label: `${option.label}${option.active ? "" : " (inactive)"}`,
                  }))}
                  onChange={(next) => updateField(field.name, next)}
                />
              );
            }

            return (
              <SelectInput
                {...common}
                value={value}
                onChange={(event) => updateField(field.name, event.target.value)}
              >
                <option value="">Select {field.label.toLowerCase()}</option>
                {choices.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                    {option.active ? "" : " (inactive)"}
                  </option>
                ))}
              </SelectInput>
            );
          }

          return (
            <TextInput
              {...common}
              type={field.type || "text"}
              inputMode={field.type === "number" ? "decimal" : undefined}
              min={field.type === "number" ? 0 : undefined}
              step={field.type === "number" ? "any" : undefined}
              placeholder={field.placeholder}
              value={value}
              onChange={(event) => updateField(field.name, event.target.value)}
            />
          );
        }}
      </Field>
    );
  };

  const formId = `resource-form-${config.endpoint.replace(/\W+/g, "-")}`;
  const readOnly = !canCreate && !canUpdate;

  // ---- Page ---------------------------------------------------------------
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={nav?.group.label}
        icon={nav?.item.icon}
        title={config.title}
        description={config.description}
        meta={
          readOnly && !loading ? (
            <Badge tone="neutral">
              <Eye size={12} aria-hidden />
              View only
            </Badge>
          ) : undefined
        }
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => void refresh()}
              disabled={loading || refreshing}
              icon={
                <RefreshCw
                  size={15}
                  aria-hidden
                  className={refreshing ? "animate-spin" : undefined}
                />
              }
            >
              Refresh
            </Button>

            {canCreate && (
              <Button onClick={openCreate} icon={<Plus size={16} aria-hidden />}>
                Add {noun.toLowerCase()}
              </Button>
            )}
          </>
        }
      />

      {config.notice && <Alert tone="info">{config.notice}</Alert>}

      {actionError && (
        <Alert tone="error" onDismiss={() => setActionError("")}>
          {actionError}
        </Alert>
      )}

      {truncated && (
        <Alert tone="info">
          Showing the first {(FETCH_PAGE_SIZE * MAX_FETCH_PAGES).toLocaleString()}{" "}
          records. Search covers only those.
        </Alert>
      )}

      <Card className="overflow-hidden">
        {/* Toolbar */}
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchInput
            value={query}
            onChange={changeQuery}
            label={`Search ${config.title.toLowerCase()}`}
            placeholder={`Search ${config.title.toLowerCase()}…`}
            className="w-full sm:max-w-xs"
          />

          {hasStatus && (
            <SegmentedControl
              label="Filter by status"
              value={status}
              onChange={changeStatus}
              options={[
                { value: "all", label: "All", count: records.length },
                { value: "active", label: "Active", count: activeCount },
                { value: "inactive", label: "Inactive", count: inactiveCount },
              ]}
            />
          )}
        </div>

        {loading ? (
          <TableSkeleton columns={Math.min(config.columns.length + 1, 5)} />
        ) : loadError && records.length === 0 ? (
          <ErrorState
            title={`Couldn't load ${config.title.toLowerCase()}`}
            message={loadError}
            onRetry={() => void refresh()}
            retrying={refreshing}
          />
        ) : records.length === 0 ? (
          <EmptyState
            icon={nav?.item.icon}
            title={`No ${config.title.toLowerCase()} yet`}
            description={
              canCreate
                ? `Add your first ${noun.toLowerCase()} to get started.`
                : "Nothing has been recorded here yet."
            }
            action={
              canCreate ? (
                <Button onClick={openCreate} icon={<Plus size={16} aria-hidden />}>
                  Add {noun.toLowerCase()}
                </Button>
              ) : undefined
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No matching records"
            description={
              needle
                ? `Nothing matches “${query.trim()}”${status !== "all" ? ` among ${status} records` : ""}.`
                : `There are no ${status} records.`
            }
            action={
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <div
            className={cn(
              "transition-opacity",
              refreshing && "pointer-events-none opacity-60"
            )}
            aria-busy={refreshing || undefined}
          >
            {loadError && (
              <div className="border-b border-slate-100 px-5 py-3">
                <Alert tone="error">
                  Refresh failed: {loadError} Showing the last loaded data.
                </Alert>
              </div>
            )}

            {/* Table on tablet and up */}
            <div className="hidden md:block">
              <Table>
                <THead>
                  <tr>
                    {config.columns.map((column) => (
                      <TH
                        key={column.key}
                        align={isNumericColumn(column) ? "right" : "left"}
                        className={column.key === "id" ? "w-20" : undefined}
                      >
                        {column.label}
                      </TH>
                    ))}
                    {hasStatus && <TH className="w-28">Status</TH>}
                    {showActions && (
                      <TH align="right" className="w-32">
                        <span className="sr-only">Actions</span>
                      </TH>
                    )}
                  </tr>
                </THead>

                <TBody>
                  {pageRows.map((record, index) => (
                    <TR
                      key={String(record.id ?? index)}
                      muted={record.is_active === false}
                    >
                      {config.columns.map((column) => (
                        <TD
                          key={column.key}
                          align={isNumericColumn(column) ? "right" : "left"}
                        >
                          {renderCell(record, column)}
                        </TD>
                      ))}
                      {hasStatus && <TD>{statusBadge(record)}</TD>}
                      {showActions && (
                        <TD align="right">{renderActions(record)}</TD>
                      )}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>

            {/* Stacked cards on phones */}
            <ul className="divide-y divide-slate-100 md:hidden">
              {pageRows.map((record, index) => {
                const details = config.columns.filter(
                  (column) => column !== primaryColumn && column.key !== "id"
                );

                return (
                  <li
                    key={String(record.id ?? index)}
                    className={cn(
                      "px-4 py-4",
                      record.is_active === false && "bg-slate-50/60"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">
                          {primaryColumn
                            ? getColumnValue(record, primaryColumn)
                            : recordLabel(record)}
                        </p>
                        <p className="mt-0.5 font-mono text-xs text-slate-500">
                          #{String(record.id ?? "")}
                        </p>
                      </div>
                      {hasStatus && statusBadge(record)}
                    </div>

                    {details.length > 0 && (
                      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                        {details.map((column) => (
                          <div key={column.key} className="min-w-0">
                            <dt className="text-xs text-slate-500">
                              {column.label}
                            </dt>
                            <dd className="truncate text-sm text-slate-800">
                              {getColumnValue(record, column)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}

                    {showActions && (
                      <div className="mt-3 -mr-1.5 flex justify-end">
                        {renderActions(record)}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>

            <Pagination
              page={currentPage}
              pageCount={pageCount}
              total={filtered.length}
              pageSize={pageSize}
              onPageChange={setPage}
              pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </div>
        )}
      </Card>

      <Modal
        open={formOpen}
        onClose={closeForm}
        dismissible={!saving}
        size={config.fields.length >= 3 ? "lg" : "md"}
        title={editingId === null ? `Add ${noun.toLowerCase()}` : `Edit ${noun.toLowerCase()}`}
        description={
          editingId === null
            ? config.description
            : `Update the details for ${recordLabel(
                records.find((record) => record.id === editingId) ?? {}
              )}.`
        }
        footer={
          <>
            <Button variant="secondary" onClick={closeForm} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form={formId} loading={saving}>
              {editingId === null ? `Create ${noun.toLowerCase()}` : "Save changes"}
            </Button>
          </>
        }
      >
        <form id={formId} onSubmit={submit}>
          {formError && (
            <Alert tone="error" className="mb-5">
              {formError}
            </Alert>
          )}

          <div className="grid gap-x-4 gap-y-5 sm:grid-cols-2">
            {config.fields.map(renderField)}
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={pending?.kind === "deactivate"}
        tone="warning"
        title={`Deactivate ${pending ? recordLabel(pending.record) : ""}?`}
        description="It stays on existing records but can no longer be selected for new entries."
        confirmLabel="Deactivate"
        busy={pendingBusy}
        onConfirm={() => void confirmPending()}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending?.kind === "delete"}
        tone="danger"
        title={`Delete ${pending ? recordLabel(pending.record) : ""} permanently?`}
        description={
          <>
            This can&apos;t be undone. If other records still reference it, the
            server will block the deletion. Deactivate it instead to keep
            history intact.
          </>
        }
        confirmLabel="Delete permanently"
        busy={pendingBusy}
        onConfirm={() => void confirmPending()}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
