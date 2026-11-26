"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import {
  CalendarDays,
  ClipboardList,
  FilterX,
  IndianRupee,
  Layers,
  Pencil,
  Plus,
  Recycle,
  RefreshCw,
  SearchX,
  Trash2,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";
import { fetchAllRecords, normalizeList } from "@/lib/api/list";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { SERIES } from "@/components/charts/tokens";
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
  controlClass,
} from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import IconButton from "@/components/ui/IconButton";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import StatCard from "@/components/ui/StatCard";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";

type MasterOption = {
  id: number;
  name: string;
  symbol?: string | null;
};

type WasteLine = {
  id: number;
  item_id: number | null;
  food_name: string;
  waste_type: "RAW_INGREDIENT" | "PREPARED_FOOD";
  menu_id: number | null;
  menu_name: string | null;
  unit_id: number;
  unit_name: string | null;
  unit_symbol: string | null;
  quantity: number | string;
  waste_stage: string;
  waste_reason: string;
  estimated_cost: number | string;
};

type WasteRecord = {
  id: number;
  waste_date: string;
  meal_session_id: number | null;
  recorded_by: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  items: WasteLine[];
};

type WasteLineForm = {
  waste_type: "RAW_INGREDIENT" | "PREPARED_FOOD";
  item_id: string;
  food_name: string;
  menu_id: string;
  unit_id: string;
  quantity: string;
  waste_stage: string;
  waste_reason: string;
  estimated_cost: string;
};

type WasteForm = {
  waste_date: string;
  meal_session_id: string;
  notes: string;
  items: WasteLineForm[];
};

const stages = [
  { value: "STORAGE", label: "Storage" },
  { value: "PREPARATION", label: "Preparation" },
  { value: "COOKING", label: "Cooking" },
  { value: "SERVING", label: "Serving" },
  { value: "AFTER_MEAL", label: "After meal" },
];

const reasons = [
  { value: "SPOILED", label: "Spoiled" },
  { value: "EXPIRED", label: "Expired" },
  { value: "DAMAGED", label: "Damaged" },
  { value: "OVERPRODUCTION", label: "Overproduction" },
  { value: "LEFTOVER", label: "Leftover" },
  { value: "PLATE_WASTE", label: "Plate waste" },
  { value: "OTHER", label: "Other" },
];

const RECORDS_PER_PAGE = 8;

function todayLocal() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function emptyLine(): WasteLineForm {
  return {
    waste_type: "RAW_INGREDIENT",
    item_id: "",
    food_name: "",
    menu_id: "",
    unit_id: "",
    quantity: "",
    waste_stage: "STORAGE",
    waste_reason: "OTHER",
    estimated_cost: "0",
  };
}

function emptyForm(): WasteForm {
  return {
    waste_date: todayLocal(),
    meal_session_id: "",
    notes: "",
    items: [emptyLine()],
  };
}

function formatDate(value: string) {
  if (!value) return "—";

  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatMoney(value: number | string) {
  return Number(value || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function titleCase(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function recordCost(record: WasteRecord) {
  return record.items.reduce(
    (total, line) => total + Number(line.estimated_cost || 0),
    0
  );
}

export default function WasteTrackingPage() {
  const { role, permissions } = useAuthorization();
  const toast = useToast();

  const canCreate = permissions.includes("waste_tracking.create");
  const canUpdate = permissions.includes("waste_tracking.update");
  const isAdmin = role === "ADMIN";

  const [records, setRecords] = useState<WasteRecord[]>([]);
  const [items, setItems] = useState<MasterOption[]>([]);
  const [units, setUnits] = useState<MasterOption[]>([]);
  const [menus, setMenus] = useState<MasterOption[]>([]);
  const [mealSessions, setMealSessions] = useState<MasterOption[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<WasteForm>(emptyForm());

  const [deleteTarget, setDeleteTarget] = useState<WasteRecord | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [filterDate, setFilterDate] = useState("");
  const [filterSession, setFilterSession] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const sessionNames = useMemo(
    () => new Map(mealSessions.map((session) => [session.id, session.name])),
    [mealSessions]
  );

  // Fetches all page data and stores it. State is updated only in the
  // promise callbacks, so this is safe to call from an effect.
  const fetchData = useCallback(() => {
    // The master lists are paginated (10 rows by default), so they are
    // loaded in full; the waste records endpoint returns everything.
    return Promise.all([
      api.get<unknown>(ENDPOINTS.wasteRecords),
      fetchAllRecords<MasterOption>(ENDPOINTS.items),
      fetchAllRecords<MasterOption>(ENDPOINTS.units),
      fetchAllRecords<MasterOption>(ENDPOINTS.menus),
      fetchAllRecords<MasterOption>(ENDPOINTS.mealSessions),
    ])
      .then(
        ([
          recordResponse,
          itemList,
          unitList,
          menuList,
          sessionList,
        ]) => {
          setRecords(normalizeList<WasteRecord>(recordResponse));
          setItems(itemList.rows);
          setUnits(unitList.rows);
          setMenus(menuList.rows);
          setMealSessions(sessionList.rows);
          setError("");
        }
      )
      .catch((err: unknown) => {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load Waste Tracking data."
        );
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  // Used by the Refresh button and after saving or deleting a record.
  const loadData = useCallback(async () => {
    setRefreshing(true);
    await fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const sessionLabel = useCallback(
    (record: WasteRecord) =>
      record.meal_session_id
        ? sessionNames.get(record.meal_session_id) ||
          `Session #${record.meal_session_id}`
        : "No meal session",
    [sessionNames]
  );

  const needle = query.trim().toLowerCase();

  const visibleRecords = useMemo(() => {
    return records.filter((record) => {
      const matchesDate =
        !filterDate || record.waste_date?.slice(0, 10) === filterDate;

      const matchesSession =
        !filterSession ||
        String(record.meal_session_id ?? "") === filterSession;

      const matchesQuery =
        !needle ||
        [
          `#${record.id}`,
          record.notes ?? "",
          sessionLabel(record),
          ...record.items.flatMap((line) => [
            line.food_name,
            line.menu_name ?? "",
            titleCase(line.waste_reason),
            titleCase(line.waste_stage),
          ]),
        ]
          .join(" ")
          .toLowerCase()
          .includes(needle);

      return matchesDate && matchesSession && matchesQuery;
    });
  }, [records, filterDate, filterSession, needle, sessionLabel]);

  const totalEstimatedCost = useMemo(
    () => visibleRecords.reduce((total, record) => total + recordCost(record), 0),
    [visibleRecords]
  );

  const totalEntries = visibleRecords.reduce(
    (total, record) => total + record.items.length,
    0
  );

  const filtersActive = Boolean(filterDate || filterSession || needle);

  const pageCount = Math.max(
    1,
    Math.ceil(visibleRecords.length / RECORDS_PER_PAGE)
  );
  const currentPage = Math.min(page, pageCount);
  const pageRecords = visibleRecords.slice(
    (currentPage - 1) * RECORDS_PER_PAGE,
    currentPage * RECORDS_PER_PAGE
  );

  function clearFilters() {
    setFilterDate("");
    setFilterSession("");
    setQuery("");
    setPage(1);
  }

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyForm());
    setFormError("");
    setFormOpen(true);
  }

  function openEditForm(record: WasteRecord) {
    setEditingId(record.id);

    setForm({
      waste_date: record.waste_date?.slice(0, 10) || todayLocal(),
      meal_session_id: record.meal_session_id
        ? String(record.meal_session_id)
        : "",
      notes: record.notes || "",
      items: record.items.map((line) => ({
        waste_type: line.waste_type,
        item_id: line.item_id ? String(line.item_id) : "",
        food_name:
          line.waste_type === "PREPARED_FOOD"
            ? line.food_name
            : "",
        menu_id: line.menu_id ? String(line.menu_id) : "",
        unit_id: String(line.unit_id),
        quantity: String(line.quantity),
        waste_stage: line.waste_stage,
        waste_reason: line.waste_reason,
        estimated_cost: String(line.estimated_cost ?? 0),
      })),
    });

    setFormError("");
    setFormOpen(true);
  }

  function closeForm() {
    if (!saving) setFormOpen(false);
  }

  function updateLine(
    index: number,
    field: keyof WasteLineForm,
    value: string
  ) {
    setForm((current) => ({
      ...current,
      items: current.items.map((line, lineIndex) =>
        lineIndex === index
          ? { ...line, [field]: value }
          : line
      ),
    }));
  }

  function addLine() {
    setForm((current) => ({
      ...current,
      items: [...current.items, emptyLine()],
    }));
  }

  function removeLine(index: number) {
    setForm((current) => ({
      ...current,
      items:
        current.items.length === 1
          ? current.items
          : current.items.filter((_, lineIndex) => lineIndex !== index),
    }));
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    try {
      const payload = {
        waste_date: form.waste_date,
        meal_session_id: form.meal_session_id
          ? Number(form.meal_session_id)
          : null,
        notes: form.notes.trim() || null,
        items: form.items.map((line) => ({
          waste_type: line.waste_type,
          item_id:
            line.waste_type === "RAW_INGREDIENT"
              ? Number(line.item_id)
              : null,
          food_name:
            line.waste_type === "PREPARED_FOOD"
              ? line.food_name.trim()
              : null,
          menu_id: line.menu_id ? Number(line.menu_id) : null,
          unit_id: Number(line.unit_id),
          quantity: Number(line.quantity),
          waste_stage: line.waste_stage,
          waste_reason: line.waste_reason,
          estimated_cost: Number(line.estimated_cost || 0),
        })),
      };

      if (editingId !== null) {
        await api.patch(
          `${ENDPOINTS.wasteRecords}/${editingId}`,
          payload
        );
        toast.success("Waste record updated.");
      } else {
        await api.post(ENDPOINTS.wasteRecords, payload);
        toast.success("Waste record saved.");
      }

      setFormOpen(false);
      setEditingId(null);
      setForm(emptyForm());
      await loadData();
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "Unable to save the waste record."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;

    setDeleting(true);
    setError("");

    try {
      await api.delete(`${ENDPOINTS.wasteRecords}/${deleteTarget.id}`);
      toast.success(`Waste record #${deleteTarget.id} deleted.`);
      setDeleteTarget(null);
      await loadData();
    } catch (err) {
      setDeleteTarget(null);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to delete the waste record."
      );
    } finally {
      setDeleting(false);
    }
  }

  const formTotal = form.items.reduce(
    (total, line) => total + (Number(line.estimated_cost) || 0),
    0
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        icon={Recycle}
        title="Waste Tracking"
        description="Record and monitor raw ingredient waste and prepared food waste. Leftovers already classified as wasted on a meal record must not be entered here again."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => void loadData()}
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
              <Button
                onClick={openCreateForm}
                icon={<Plus size={16} aria-hidden />}
              >
                Record waste
              </Button>
            )}
          </>
        }
      />

      {error && records.length > 0 && (
        <Alert tone="error" onDismiss={() => setError("")}>
          {error}
        </Alert>
      )}

      {/* Figures follow the filters, so they always describe what's listed. */}
      <section
        aria-label="Waste summary"
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      >
        {loading ? (
          Array.from({ length: 3 }, (_, index) => (
            <div
              key={index}
              className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card"
            >
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="mt-4 h-7 w-20" />
            </div>
          ))
        ) : (
          <>
            <StatCard
              label="Waste records"
              value={visibleRecords.length.toLocaleString("en-IN")}
              description={filtersActive ? "Matching current filters" : "All records"}
              icon={ClipboardList}
            />
            <StatCard
              label="Waste entries"
              value={totalEntries.toLocaleString("en-IN")}
              description="Individual items across records"
              icon={Layers}
            />
            <StatCard
              label="Estimated waste cost"
              value={`₹${formatMoney(totalEstimatedCost)}`}
              description={filtersActive ? "Matching current filters" : "All records"}
              icon={IndianRupee}
              accent={SERIES.orange}
            />
          </>
        )}
      </section>

      <Card className="overflow-hidden">
        {/* Filters */}
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-3 lg:flex-row lg:items-center">
          <SearchInput
            value={query}
            onChange={(value) => {
              setQuery(value);
              setPage(1);
            }}
            label="Search waste records"
            placeholder="Search food, menu, reason, notes…"
            className="w-full lg:max-w-xs"
          />

          <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:flex lg:items-center">
            <div className="relative">
              <CalendarDays
                size={15}
                aria-hidden
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
              />
              <input
                type="date"
                value={filterDate}
                onChange={(event) => {
                  setFilterDate(event.target.value);
                  setPage(1);
                }}
                aria-label="Filter by date"
                className={cn(controlClass, "h-9 pl-9 lg:w-44")}
              />
            </div>

            <SelectInput
              value={filterSession}
              onChange={(event) => {
                setFilterSession(event.target.value);
                setPage(1);
              }}
              aria-label="Filter by meal session"
              className="h-9 lg:w-48"
            >
              <option value="">All meal sessions</option>
              {mealSessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.name}
                </option>
              ))}
            </SelectInput>
          </div>

          {filtersActive && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              icon={<FilterX size={14} aria-hidden />}
              className="self-start lg:ml-auto lg:self-center"
            >
              Clear filters
            </Button>
          )}
        </div>

        {loading ? (
          <div className="space-y-4 p-5" role="status" aria-label="Loading">
            {Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-4">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="mt-3 h-3 w-64" />
                <Skeleton className="mt-5 h-16 w-full" />
              </div>
            ))}
          </div>
        ) : error && records.length === 0 ? (
          <ErrorState
            title="Couldn't load waste records"
            message={error}
            onRetry={() => void loadData()}
            retrying={refreshing}
          />
        ) : records.length === 0 ? (
          <EmptyState
            icon={Recycle}
            title="No waste recorded yet"
            description="Record raw ingredient or prepared food waste to start tracking where food is lost."
            action={
              canCreate ? (
                <Button
                  onClick={openCreateForm}
                  icon={<Plus size={16} aria-hidden />}
                >
                  Record waste
                </Button>
              ) : undefined
            }
          />
        ) : visibleRecords.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No matching waste records"
            description="Try a different date, meal session or search term."
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
            <ul className="space-y-4 p-4 sm:p-5">
              {pageRecords.map((record) => (
                <li
                  key={record.id}
                  className="overflow-hidden rounded-xl border border-slate-200"
                >
                  <article aria-labelledby={`waste-${record.id}`}>
                    <div className="flex flex-col gap-3 border-b border-slate-100 bg-slate-50/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3
                            id={`waste-${record.id}`}
                            className="font-semibold text-slate-900"
                          >
                            Record #{record.id}
                          </h3>
                          <Badge tone="brand">
                            {formatDate(record.waste_date)}
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {sessionLabel(record)} · {record.items.length}{" "}
                          {record.items.length === 1 ? "entry" : "entries"}
                        </p>
                      </div>

                      <div className="flex items-center justify-between gap-2 sm:justify-end">
                        <p className="text-sm font-semibold text-slate-900 tabular-nums">
                          ₹{formatMoney(recordCost(record))}
                        </p>

                        <div className="flex items-center">
                          {canUpdate && (
                            <IconButton
                              size="sm"
                              tone="brand"
                              icon={<Pencil size={15} />}
                              label={`Edit waste record ${record.id}`}
                              onClick={() => openEditForm(record)}
                            />
                          )}

                          {isAdmin && (
                            <IconButton
                              size="sm"
                              tone="danger"
                              icon={<Trash2 size={15} />}
                              label={`Delete waste record ${record.id}`}
                              onClick={() => setDeleteTarget(record)}
                            />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Line table on tablet and up */}
                    <div className="hidden md:block">
                      <Table>
                        <THead>
                          <tr>
                            <TH>Food / item</TH>
                            <TH>Type</TH>
                            <TH align="right">Quantity</TH>
                            <TH>Stage</TH>
                            <TH>Reason</TH>
                            <TH align="right">Cost</TH>
                          </tr>
                        </THead>
                        <TBody>
                          {record.items.map((line) => (
                            <TR key={line.id}>
                              <TD>
                                <p className="font-medium text-slate-900">
                                  {line.food_name}
                                </p>
                                {line.menu_name && (
                                  <p className="mt-0.5 text-xs text-slate-500">
                                    Menu: {line.menu_name}
                                  </p>
                                )}
                              </TD>
                              <TD>
                                <Badge
                                  tone={
                                    line.waste_type === "RAW_INGREDIENT"
                                      ? "neutral"
                                      : "warning"
                                  }
                                >
                                  {line.waste_type === "RAW_INGREDIENT"
                                    ? "Raw ingredient"
                                    : "Prepared food"}
                                </Badge>
                              </TD>
                              <TD align="right">
                                {line.quantity}{" "}
                                <span className="text-slate-500">
                                  {line.unit_symbol || line.unit_name || ""}
                                </span>
                              </TD>
                              <TD>{titleCase(line.waste_stage)}</TD>
                              <TD>{titleCase(line.waste_reason)}</TD>
                              <TD
                                align="right"
                                className="font-medium text-slate-900"
                              >
                                ₹{formatMoney(line.estimated_cost)}
                              </TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    </div>

                    {/* Stacked lines on phones */}
                    <ul className="divide-y divide-slate-100 md:hidden">
                      {record.items.map((line) => (
                        <li key={line.id} className="px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium text-slate-900">
                                {line.food_name}
                              </p>
                              <p className="mt-0.5 text-xs text-slate-500">
                                {line.quantity}{" "}
                                {line.unit_symbol || line.unit_name || ""} ·{" "}
                                {titleCase(line.waste_stage)} ·{" "}
                                {titleCase(line.waste_reason)}
                              </p>
                            </div>
                            <p className="shrink-0 text-sm font-medium text-slate-900 tabular-nums">
                              ₹{formatMoney(line.estimated_cost)}
                            </p>
                          </div>
                          {line.menu_name && (
                            <p className="mt-1 text-xs text-slate-500">
                              Menu: {line.menu_name}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>

                    {record.notes && (
                      <p className="border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
                        <span className="font-medium text-slate-700">
                          Notes:{" "}
                        </span>
                        {record.notes}
                      </p>
                    )}
                  </article>
                </li>
              ))}
            </ul>

            <Pagination
              page={currentPage}
              pageCount={pageCount}
              total={visibleRecords.length}
              pageSize={RECORDS_PER_PAGE}
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      <Modal
        open={formOpen}
        onClose={closeForm}
        dismissible={!saving}
        size="xl"
        title={editingId !== null ? `Edit waste record #${editingId}` : "Record waste"}
        description="Add raw ingredient or prepared food waste entries."
        footer={
          <>
            <p className="mr-auto hidden self-center text-sm text-slate-500 sm:block">
              Total estimated cost{" "}
              <span className="font-semibold text-slate-900 tabular-nums">
                ₹{formatMoney(formTotal)}
              </span>
            </p>
            <Button variant="secondary" onClick={closeForm} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="waste-form" loading={saving}>
              {editingId !== null ? "Save changes" : "Save waste record"}
            </Button>
          </>
        }
      >
        <form id="waste-form" onSubmit={handleSubmit} className="space-y-6">
          {formError && <Alert tone="error">{formError}</Alert>}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Waste date" required>
              {({ id }) => (
                <TextInput
                  id={id}
                  type="date"
                  required
                  data-autofocus
                  value={form.waste_date}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      waste_date: event.target.value,
                    }))
                  }
                />
              )}
            </Field>

            <Field label="Meal session" hint="Optional">
              {({ id, describedBy }) => (
                <SelectInput
                  id={id}
                  aria-describedby={describedBy}
                  value={form.meal_session_id}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      meal_session_id: event.target.value,
                    }))
                  }
                >
                  <option value="">No meal session</option>
                  {mealSessions.map((session) => (
                    <option key={session.id} value={session.id}>
                      {session.name}
                    </option>
                  ))}
                </SelectInput>
              )}
            </Field>
          </div>

          <fieldset className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <legend className="text-sm font-semibold text-slate-900">
                Waste entries
                <span className="ml-2 font-normal text-slate-500">
                  {form.items.length}
                </span>
              </legend>

              <Button
                variant="secondary"
                size="sm"
                onClick={addLine}
                icon={<Plus size={14} aria-hidden />}
              >
                Add entry
              </Button>
            </div>

            {form.items.map((line, index) => (
              <div
                key={index}
                className="rounded-xl border border-slate-200 bg-slate-50/50 p-4"
              >
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
                      {index + 1}
                    </span>
                    <SegmentedControl
                      label={`Entry ${index + 1} waste type`}
                      value={line.waste_type}
                      onChange={(value) => {
                        updateLine(index, "waste_type", value);
                        updateLine(index, "item_id", "");
                        updateLine(index, "food_name", "");
                      }}
                      options={[
                        { value: "RAW_INGREDIENT", label: "Raw ingredient" },
                        { value: "PREPARED_FOOD", label: "Prepared food" },
                      ]}
                    />
                  </div>

                  {form.items.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeLine(index)}
                      icon={<Trash2 size={14} aria-hidden />}
                      className="text-red-700 hover:bg-red-50 hover:text-red-800"
                    >
                      Remove
                    </Button>
                  )}
                </div>

                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {line.waste_type === "RAW_INGREDIENT" ? (
                    <Field
                      label="Inventory item"
                      required
                      className="sm:col-span-2 lg:col-span-3"
                    >
                      {({ id }) => (
                        <SearchSelect
                          id={id}
                          required
                          requiredMessage="Select an inventory item."
                          value={line.item_id}
                          noun="items"
                          placeholder="Select inventory item"
                          options={items.map((item) => ({ value: String(item.id), label: item.name }))}
                          onChange={(value) => updateLine(index, "item_id", value)}
                        />
                      )}
                    </Field>
                  ) : (
                    <>
                      <Field
                        label="Prepared food name"
                        required
                        className="lg:col-span-2"
                      >
                        {({ id }) => (
                          <TextInput
                            id={id}
                            required
                            maxLength={150}
                            value={line.food_name}
                            onChange={(event) =>
                              updateLine(index, "food_name", event.target.value)
                            }
                            placeholder="e.g. Vegetable biryani"
                          />
                        )}
                      </Field>

                      <Field label="Related menu" hint="Optional">
                        {({ id, describedBy }) => (
                          <SelectInput
                            id={id}
                            aria-describedby={describedBy}
                            value={line.menu_id}
                            onChange={(event) =>
                              updateLine(index, "menu_id", event.target.value)
                            }
                          >
                            <option value="">No related menu</option>
                            {menus.map((menu) => (
                              <option key={menu.id} value={menu.id}>
                                {menu.name}
                              </option>
                            ))}
                          </SelectInput>
                        )}
                      </Field>
                    </>
                  )}

                  <Field label="Quantity" required>
                    {({ id }) => (
                      <TextInput
                        id={id}
                        type="number"
                        inputMode="decimal"
                        required
                        min="0.001"
                        step="0.001"
                        value={line.quantity}
                        onChange={(event) =>
                          updateLine(index, "quantity", event.target.value)
                        }
                        placeholder="e.g. 2.500"
                      />
                    )}
                  </Field>

                  <Field label="Unit" required>
                    {({ id }) => (
                      <SelectInput
                        id={id}
                        required
                        value={line.unit_id}
                        onChange={(event) =>
                          updateLine(index, "unit_id", event.target.value)
                        }
                      >
                        <option value="">Select unit</option>
                        {units.map((unit) => (
                          <option key={unit.id} value={unit.id}>
                            {unit.name}
                            {unit.symbol ? ` (${unit.symbol})` : ""}
                          </option>
                        ))}
                      </SelectInput>
                    )}
                  </Field>

                  <Field label="Estimated cost (₹)" required>
                    {({ id }) => (
                      <TextInput
                        id={id}
                        type="number"
                        inputMode="decimal"
                        required
                        min="0"
                        step="0.01"
                        value={line.estimated_cost}
                        onChange={(event) =>
                          updateLine(index, "estimated_cost", event.target.value)
                        }
                      />
                    )}
                  </Field>

                  <Field label="Waste stage" required>
                    {({ id }) => (
                      <SelectInput
                        id={id}
                        required
                        value={line.waste_stage}
                        onChange={(event) =>
                          updateLine(index, "waste_stage", event.target.value)
                        }
                      >
                        {stages.map((stage) => (
                          <option key={stage.value} value={stage.value}>
                            {stage.label}
                          </option>
                        ))}
                      </SelectInput>
                    )}
                  </Field>

                  <Field label="Waste reason" required>
                    {({ id }) => (
                      <SelectInput
                        id={id}
                        required
                        value={line.waste_reason}
                        onChange={(event) =>
                          updateLine(index, "waste_reason", event.target.value)
                        }
                      >
                        {reasons.map((reason) => (
                          <option key={reason.value} value={reason.value}>
                            {reason.label}
                          </option>
                        ))}
                      </SelectInput>
                    )}
                  </Field>
                </div>
              </div>
            ))}
          </fieldset>

          <Field label="Notes" hint="Optional · up to 2,000 characters">
            {({ id, describedBy }) => (
              <TextArea
                id={id}
                aria-describedby={describedBy}
                maxLength={2000}
                value={form.notes}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
                placeholder="Additional details about this waste record…"
              />
            )}
          </Field>

          <p className="text-sm text-slate-500 sm:hidden">
            Total estimated cost{" "}
            <span className="font-semibold text-slate-900 tabular-nums">
              ₹{formatMoney(formTotal)}
            </span>
          </p>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        tone="danger"
        title={`Delete waste record #${deleteTarget?.id ?? ""}?`}
        description={
          deleteTarget ? (
            <>
              This permanently removes the record from{" "}
              <strong className="font-semibold text-slate-800">
                {formatDate(deleteTarget.waste_date)}
              </strong>{" "}
              with {deleteTarget.items.length}{" "}
              {deleteTarget.items.length === 1 ? "entry" : "entries"} worth ₹
              {formatMoney(recordCost(deleteTarget))}. This can&apos;t be
              undone.
            </>
          ) : (
            ""
          )
        }
        confirmLabel="Delete record"
        busy={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
