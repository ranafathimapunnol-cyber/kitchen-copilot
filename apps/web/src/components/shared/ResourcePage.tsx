"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  X,
  Ban,
} from "lucide-react";
import { api } from "@/lib/api/client";
import type {
  FieldConfig,
  ResourceConfig,
  SelectOption,
} from "@/types";
import Button from "@/components/ui/Button";

type RecordItem = Record<string, unknown>;

type PaginatedResponse = {
  items?: RecordItem[];
  page?: number;
  page_size?: number;
  total?: number;
  total_pages?: number;
};

const PAGE_SIZE = 10;

function normalizeList(data: unknown): RecordItem[] {
  if (Array.isArray(data)) return data as RecordItem[];

  if (data && typeof data === "object") {
    const object = data as Record<string, unknown>;

    for (const key of ["items", "results", "data"]) {
      if (Array.isArray(object[key])) {
        return object[key] as RecordItem[];
      }
    }
  }

  return [];
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function getPaginatedUrl(endpoint: string, page: number): string {
  const separator = endpoint.includes("?") ? "&" : "?";
  return `${endpoint}${separator}page=${page}&page_size=${PAGE_SIZE}`;
}

export default function ResourcePage({
  config,
}: {
  config: ResourceConfig;
}) {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [options, setOptions] = useState<Record<string, SelectOption[]>>({});
  const [form, setForm] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState<string | number | null>(null);

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadData = useCallback(async (targetPage = page) => {
    setLoading(true);
    setError("");

    try {
      const list = await api.get<unknown>(
        getPaginatedUrl(config.endpoint, targetPage),
      );

      const rows = normalizeList(list);
      const pagination = (
        list && typeof list === "object" && !Array.isArray(list)
          ? list
          : {}
      ) as PaginatedResponse;

      const nextTotal = pagination.total ?? rows.length;
      const nextTotalPages = Math.max(
        1,
        pagination.total_pages ??
          Math.ceil(nextTotal / PAGE_SIZE),
      );

      if (targetPage > nextTotalPages) {
        setPage(nextTotalPages);
        return;
      }

      setRecords(rows);
      setTotal(nextTotal);
      setTotalPages(nextTotalPages);

      const optionFields = config.fields.filter(
        (field) => field.optionsEndpoint,
      );

      const optionResults = await Promise.all(
        optionFields.map(async (field) => {
          const data = await api.get<unknown>(
            getPaginatedUrl(field.optionsEndpoint!, 1),
          );

          const optionRows = normalizeList(data);

          return [
            field.name,
            optionRows
              .filter((row) => row.is_active !== false)
              .map((row) => ({
                value: String(row.id ?? row.value ?? ""),
                label: String(
                  row[field.optionLabel || "name"] ??
                    row.name ??
                    row.title ??
                    row.id ??
                    "",
                ),
              })),
          ] as const;
        }),
      );

      setOptions(Object.fromEntries(optionResults));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load records.",
      );
    } finally {
      setLoading(false);
    }
  }, [config, page]);

  useEffect(() => {
    let cancelled = false;

    const timer = setTimeout(() => {
      if (!cancelled) {
        void loadData();
      }
    }, 0);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [loadData]);

  const resetForm = () => {
    setForm({});
    setEditingId(null);
  };

  const updateField = (name: string, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
  };

  const startEdit = (record: RecordItem) => {
    if (record.is_active === false) return;

    const nextForm: Record<string, string> = {};

    for (const field of config.fields) {
      const value = record[field.name];

      nextForm[field.name] =
        value === null || value === undefined ? "" : String(value);
    }

    setForm(nextForm);
    setEditingId(record.id as string | number);
    setError("");
    setSuccess("");
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");

    try {
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
              `${field.label} must be a valid non-negative number.`,
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
          payload,
        );

        setSuccess("Record updated successfully.");
        resetForm();
        await loadData(page);
      } else {
        await api.post(config.endpoint, payload);

        setSuccess("Record created successfully.");
        resetForm();

        if (page !== 1) {
          setPage(1);
        } else {
          await loadData(1);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save record.");
    } finally {
      setSaving(false);
    }
  };

  const deactivateRecord = async (record: RecordItem) => {
    if (record.id === undefined || record.id === null) return;

    const id = record.id as string | number;

    if (
      !window.confirm(
        "Are you sure you want to deactivate this record? It will no longer be available for new selections.",
      )
    ) {
      return;
    }

    setDeletingId(id);
    setError("");
    setSuccess("");

    try {
      const result = await api.post<{ message?: string }>(
        `${config.endpoint}/${encodeURIComponent(String(id))}/deactivate`,
        {},
      );

      if (editingId === id) resetForm();

      setSuccess(result?.message || "Record deactivated successfully.");
      await loadData(page);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to deactivate record.",
      );
    } finally {
      setDeletingId(null);
    }
  };

  const deleteRecord = async (record: RecordItem) => {
    if (record.id === undefined || record.id === null) return;

    const id = record.id as string | number;

    if (
      !window.confirm(
        "Permanently delete this record? This action cannot be undone. If other records reference it, deletion will be blocked.",
      )
    ) {
      return;
    }

    setDeletingId(id);
    setError("");
    setSuccess("");

    try {
      const result = await api.delete<{ message?: string }>(
        `${config.endpoint}/${encodeURIComponent(String(id))}`,
      );

      if (editingId === id) resetForm();

      setSuccess(result?.message || "Record permanently deleted.");
      await loadData(page);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete record.",
      );
    } finally {
      setDeletingId(null);
    }
  };

  const getColumnValue = (
    record: RecordItem,
    column: ResourceConfig["columns"][number],
  ) => {
    const fieldName = column.optionField || column.key;
    const rawValue = record[column.key];

    const field = config.fields.find(
      (item) => item.name === fieldName,
    );

    const availableOptions =
      options[fieldName] || field?.options || [];

    const matchedOption = availableOptions.find(
      (option) => option.value === String(rawValue ?? ""),
    );

    return matchedOption?.label ?? displayValue(rawValue);
  };

  const renderField = (field: FieldConfig) => {
    const common =
      "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100";

    const fieldOptions = field.options || options[field.name] || [];

    return (
      <label key={field.name} className="block space-y-1.5">
        <span className="text-sm font-medium text-slate-700">
          {field.label}
          {field.required && <span className="text-red-500"> *</span>}
        </span>

        {field.type === "textarea" ? (
          <textarea
            className={`${common} min-h-24`}
            placeholder={field.placeholder}
            required={field.required}
            value={form[field.name] || ""}
            onChange={(event) =>
              updateField(field.name, event.target.value)
            }
          />
        ) : field.type === "select" ? (
          <select
            className={common}
            required={field.required}
            value={form[field.name] || ""}
            onChange={(event) =>
              updateField(field.name, event.target.value)
            }
          >
            <option value="">
              Select {field.label.toLowerCase()}
            </option>

            {fieldOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            className={common}
            type={field.type || "text"}
            min={field.type === "number" ? 0 : undefined}
            step={field.type === "number" ? "any" : undefined}
            placeholder={field.placeholder}
            required={field.required}
            value={form[field.name] || ""}
            onChange={(event) =>
              updateField(field.name, event.target.value)
            }
          />
        )}
      </label>
    );
  };

  const firstRecord = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastRecord = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {config.title}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {config.description}
          </p>
        </div>

        <Button onClick={() => void loadData(page)} disabled={loading}>
          <RefreshCw size={16} className="mr-2" />
          Refresh
        </Button>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {success && (
        <div
          role="status"
          className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700"
        >
          {success}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">
            Records
          </h2>

          {loading ? (
            <p className="py-8 text-center text-sm text-slate-500">
              Loading records...
            </p>
          ) : records.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">
              No records found.
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                      {config.columns.map((field) => (
                        <th
                          key={field.key}
                          className="px-3 py-3 font-semibold"
                        >
                          {field.label}
                        </th>
                      ))}

                      <th className="px-3 py-3 font-semibold">Status</th>
                      <th className="px-3 py-3 font-semibold">Actions</th>
                    </tr>
                  </thead>

                  <tbody>
                    {records.map((record, index) => {
                      const inactive = record.is_active === false;
                      const hasActiveStatus =
                        typeof record.is_active === "boolean";
                      const id = record.id as
                        | string
                        | number
                        | undefined;
                      const busy = deletingId === id;

                      return (
                        <tr
                          key={String(id ?? index)}
                          className="border-b border-slate-100 last:border-0"
                        >
                          {config.columns.map((field) => (
                            <td
                              key={field.key}
                              className="px-3 py-3 text-slate-700"
                            >
                              {getColumnValue(record, field)}
                            </td>
                          ))}

                          <td className="px-3 py-3">
                            {hasActiveStatus ? (
                              <span
                                className={
                                  inactive
                                    ? "text-slate-500"
                                    : "font-medium text-blue-700"
                                }
                              >
                                {inactive ? "Inactive" : "Active"}
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>

                          <td className="px-3 py-3">
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                title="Edit record"
                                aria-label="Edit record"
                                disabled={
                                  inactive ||
                                  id === undefined ||
                                  busy
                                }
                                onClick={() => startEdit(record)}
                                className="rounded-md p-2 text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-30"
                              >
                                <Pencil size={16} />
                              </button>

                              {hasActiveStatus && !inactive && (
                                <button
                                  type="button"
                                  title="Deactivate record"
                                  aria-label="Deactivate record"
                                  disabled={id === undefined || busy}
                                  onClick={() =>
                                    void deactivateRecord(record)
                                  }
                                  className="rounded-md p-2 text-amber-600 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-30"
                                >
                                  <Ban size={16} />
                                </button>
                              )}

                              <button
                                type="button"
                                title="Permanently delete record"
                                aria-label="Permanently delete record"
                                disabled={id === undefined || busy}
                                onClick={() =>
                                  void deleteRecord(record)
                                }
                                className="rounded-md p-2 text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-30"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                <p className="text-sm text-slate-500">
                  Showing {firstRecord}–{lastRecord} of {total} records
                </p>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={page <= 1 || loading}
                    onClick={() => setPage((current) => current - 1)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous
                  </button>

                  <span className="text-sm text-slate-600">
                    Page {page} of {totalPages}
                  </span>

                  <button
                    type="button"
                    disabled={page >= totalPages || loading}
                    onClick={() => setPage((current) => current + 1)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {editingId === null ? (
                <Plus size={18} className="text-blue-700" />
              ) : (
                <Pencil size={18} className="text-blue-700" />
              )}

              <h2 className="text-lg font-semibold text-slate-900">
                {editingId === null
                  ? `Add ${config.title}`
                  : `Edit ${config.title}`}
              </h2>
            </div>

            {editingId !== null && (
              <button
                type="button"
                onClick={resetForm}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
              >
                <X size={15} />
                Cancel
              </button>
            )}
          </div>

          <form onSubmit={submit} className="space-y-4">
            {config.fields.map(renderField)}

            <Button type="submit" disabled={saving}>
              {saving
                ? "Saving..."
                : editingId === null
                  ? "Create record"
                  : "Update record"}
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
