"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  X,
  Recycle,
  ClipboardList,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";
import { useAuthorization } from "@/components/layout/AuthorizationContext";

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

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100";

const labelClass =
  "block text-sm font-medium text-slate-700";

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

function normalizeList<T>(value: unknown): T[] {
  if (Array.isArray(value)) {
    return value as T[];
  }

  if (value && typeof value === "object") {
    const data = value as Record<string, unknown>;

    if (Array.isArray(data.items)) return data.items as T[];
    if (Array.isArray(data.results)) return data.results as T[];
    if (Array.isArray(data.data)) return data.data as T[];
  }

  return [];
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

export default function WasteTrackingPage() {
  const { role, permissions } = useAuthorization();

  const canCreate = permissions.includes("waste_tracking.create");
  const canUpdate = permissions.includes("waste_tracking.update");
  const isAdmin = role === "ADMIN";

  const [records, setRecords] = useState<WasteRecord[]>([]);
  const [items, setItems] = useState<MasterOption[]>([]);
  const [units, setUnits] = useState<MasterOption[]>([]);
  const [menus, setMenus] = useState<MasterOption[]>([]);
  const [mealSessions, setMealSessions] = useState<MasterOption[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<WasteForm>(emptyForm());

  const [filterDate, setFilterDate] = useState("");
  const [filterSession, setFilterSession] = useState("");

  const sessionNames = useMemo(
    () => new Map(mealSessions.map((session) => [session.id, session.name])),
    [mealSessions]
  );

  // Fetches all page data and stores it. State is updated only in the
  // promise callbacks, so this is safe to call from an effect.
  const fetchData = useCallback(() => {
    return Promise.all([
      api.get<unknown>(ENDPOINTS.wasteRecords),
      api.get<unknown>(ENDPOINTS.items),
      api.get<unknown>(ENDPOINTS.units),
      api.get<unknown>(ENDPOINTS.menus),
      api.get<unknown>(ENDPOINTS.mealSessions),
    ])
      .then(
        ([
          recordResponse,
          itemResponse,
          unitResponse,
          menuResponse,
          sessionResponse,
        ]) => {
          setRecords(normalizeList<WasteRecord>(recordResponse));
          setItems(normalizeList<MasterOption>(itemResponse));
          setUnits(normalizeList<MasterOption>(unitResponse));
          setMenus(normalizeList<MasterOption>(menuResponse));
          setMealSessions(normalizeList<MasterOption>(sessionResponse));
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
      });
  }, []);

  // Used by the Refresh button and after saving or deleting a record.
  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    await fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const visibleRecords = useMemo(() => {
    return records.filter((record) => {
      const matchesDate =
        !filterDate || record.waste_date?.slice(0, 10) === filterDate;

      const matchesSession =
        !filterSession ||
        String(record.meal_session_id ?? "") === filterSession;

      return matchesDate && matchesSession;
    });
  }, [records, filterDate, filterSession]);

  const totalEstimatedCost = useMemo(() => {
    return visibleRecords.reduce(
      (recordTotal, record) =>
        recordTotal +
        record.items.reduce(
          (lineTotal, line) =>
            lineTotal + Number(line.estimated_cost || 0),
          0
        ),
      0
    );
  }, [visibleRecords]);

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyForm());
    setError("");
    setSuccess("");
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

    setError("");
    setSuccess("");
    setFormOpen(true);
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

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");

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
        setSuccess("Waste record updated successfully.");
      } else {
        await api.post(ENDPOINTS.wasteRecords, payload);
        setSuccess("Waste record created successfully.");
      }

      setFormOpen(false);
      setEditingId(null);
      setForm(emptyForm());
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save the waste record."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(recordId: number) {
    const confirmed = window.confirm(
      "Are you sure you want to delete this waste record?"
    );

    if (!confirmed) return;

    setError("");
    setSuccess("");

    try {
      await api.delete(`${ENDPOINTS.wasteRecords}/${recordId}`);
      setSuccess("Waste record deleted successfully.");
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to delete the waste record."
      );
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2 text-blue-700">
            <Recycle size={20} />
            <p className="text-xs font-bold uppercase tracking-widest">
              Kitchen Operations
            </p>
          </div>

          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Waste Tracking
          </h1>

          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Record and monitor raw ingredient waste and prepared food waste.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>

          {canCreate && (
            <button
              type="button"
              onClick={openCreateForm}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800"
            >
              <Plus size={17} />
              Record Waste
            </button>
          )}
        </div>
      </section>

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
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
        >
          {success}
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Waste records</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {visibleRecords.length}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Waste entries</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            {visibleRecords.reduce(
              (total, record) => total + record.items.length,
              0
            )}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Estimated waste cost</p>
          <p className="mt-2 text-2xl font-bold text-slate-900">
            ₹{formatMoney(totalEstimatedCost)}
          </p>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-4 flex items-center gap-2">
          <ClipboardList size={18} className="text-slate-500" />
          <h2 className="font-semibold text-slate-900">Waste records</h2>
        </div>

        <div className="mb-5 grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Filter by date</label>
            <input
              type="date"
              value={filterDate}
              onChange={(event) => setFilterDate(event.target.value)}
              className={inputClass}
            />
          </div>

          <div>
            <label className={labelClass}>Filter by meal session</label>
            <select
              value={filterSession}
              onChange={(event) => setFilterSession(event.target.value)}
              className={inputClass}
            >
              <option value="">All meal sessions</option>
              {mealSessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-slate-500">
            Loading waste records...
          </div>
        ) : visibleRecords.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 px-5 py-12 text-center">
            <Recycle size={30} className="mx-auto text-slate-400" />
            <h3 className="mt-3 font-semibold text-slate-800">
              No waste records found
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Create a waste record to start tracking kitchen waste.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {visibleRecords.map((record) => {
              const recordCost = record.items.reduce(
                (total, line) =>
                  total + Number(line.estimated_cost || 0),
                0
              );

              return (
                <article
                  key={record.id}
                  className="overflow-hidden rounded-xl border border-slate-200"
                >
                  <div className="flex flex-col justify-between gap-3 bg-slate-50 px-4 py-4 sm:flex-row sm:items-center">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold text-slate-900">
                          Waste Record #{record.id}
                        </h3>
                        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                          {formatDate(record.waste_date)}
                        </span>
                      </div>

                      <p className="mt-1 text-xs text-slate-500">
                        Meal session:{" "}
                        {record.meal_session_id
                          ? sessionNames.get(record.meal_session_id) ||
                            `Session #${record.meal_session_id}`
                          : "Not specified"}
                        {" · "}
                        {record.items.length} entr
                        {record.items.length === 1 ? "y" : "ies"}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <p className="mr-2 text-sm font-semibold text-slate-800">
                        ₹{formatMoney(recordCost)}
                      </p>

                      {canUpdate && (
                        <button
                          type="button"
                          onClick={() => openEditForm(record)}
                          aria-label={`Edit waste record ${record.id}`}
                          className="rounded-lg border border-slate-300 bg-white p-2 text-slate-600 hover:border-blue-300 hover:text-blue-700"
                        >
                          <Pencil size={16} />
                        </button>
                      )}

                      {isAdmin && (
                        <button
                          type="button"
                          onClick={() => handleDelete(record.id)}
                          aria-label={`Delete waste record ${record.id}`}
                          className="rounded-lg border border-slate-300 bg-white p-2 text-slate-600 hover:border-red-300 hover:text-red-600"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[700px] text-left text-sm">
                      <thead className="border-b border-slate-200 bg-white text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-4 py-3 font-semibold">Food / Item</th>
                          <th className="px-4 py-3 font-semibold">Type</th>
                          <th className="px-4 py-3 font-semibold">Quantity</th>
                          <th className="px-4 py-3 font-semibold">Stage</th>
                          <th className="px-4 py-3 font-semibold">Reason</th>
                          <th className="px-4 py-3 text-right font-semibold">Cost</th>
                        </tr>
                      </thead>

                      <tbody className="divide-y divide-slate-100">
                        {record.items.map((line) => (
                          <tr key={line.id}>
                            <td className="px-4 py-3">
                              <p className="font-medium text-slate-800">
                                {line.food_name}
                              </p>
                              {line.menu_name && (
                                <p className="mt-0.5 text-xs text-slate-500">
                                  Menu: {line.menu_name}
                                </p>
                              )}
                            </td>

                            <td className="px-4 py-3 text-slate-600">
                              {line.waste_type === "RAW_INGREDIENT"
                                ? "Raw ingredient"
                                : "Prepared food"}
                            </td>

                            <td className="px-4 py-3 text-slate-700">
                              {line.quantity}{" "}
                              {line.unit_symbol || line.unit_name || ""}
                            </td>

                            <td className="px-4 py-3 text-slate-600">
                              {titleCase(line.waste_stage)}
                            </td>

                            <td className="px-4 py-3 text-slate-600">
                              {titleCase(line.waste_reason)}
                            </td>

                            <td className="px-4 py-3 text-right font-medium text-slate-800">
                              ₹{formatMoney(line.estimated_cost)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {record.notes && (
                    <div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
                      <span className="font-medium text-slate-700">Notes: </span>
                      {record.notes}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {formOpen && (
        <div className="fixed inset-0 z-[70] overflow-y-auto bg-slate-950/50 p-3 sm:p-6">
          <div className="mx-auto my-4 w-full max-w-4xl rounded-2xl bg-white shadow-2xl sm:my-8">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 sm:px-6">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  {editingId !== null ? "Edit Waste Record" : "Record Waste"}
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  Add raw ingredient or prepared food waste entries.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setFormOpen(false)}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
                aria-label="Close form"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6 p-5 sm:p-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className={labelClass}>Waste date *</label>
                  <input
                    type="date"
                    required
                    value={form.waste_date}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        waste_date: event.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>

                <div>
                  <label className={labelClass}>Meal session</label>
                  <select
                    value={form.meal_session_id}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        meal_session_id: event.target.value,
                      }))
                    }
                    className={inputClass}
                  >
                    <option value="">Select meal session (optional)</option>
                    {mealSessions.map((session) => (
                      <option key={session.id} value={session.id}>
                        {session.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold text-slate-900">
                    Waste entries
                  </h3>

                  <button
                    type="button"
                    onClick={addLine}
                    className="inline-flex items-center gap-2 rounded-lg border border-blue-200 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
                  >
                    <Plus size={16} />
                    Add another item
                  </button>
                </div>

                {form.items.map((line, index) => (
                  <div
                    key={index}
                    className="space-y-4 rounded-xl border border-slate-200 p-4"
                  >
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-slate-800">
                        Entry {index + 1}
                      </h4>

                      {form.items.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeLine(index)}
                          className="inline-flex items-center gap-1 text-xs font-medium text-red-600 hover:text-red-700"
                        >
                          <Trash2 size={14} />
                          Remove
                        </button>
                      )}
                    </div>

                    <div>
                      <label className={labelClass}>Waste type *</label>
                      <select
                        required
                        value={line.waste_type}
                        onChange={(event) => {
                          const value = event.target.value as WasteLineForm["waste_type"];
                          updateLine(index, "waste_type", value);
                          updateLine(index, "item_id", "");
                          updateLine(index, "food_name", "");
                        }}
                        className={inputClass}
                      >
                        <option value="RAW_INGREDIENT">Raw ingredient</option>
                        <option value="PREPARED_FOOD">Prepared food</option>
                      </select>
                    </div>

                    {line.waste_type === "RAW_INGREDIENT" ? (
                      <div>
                        <label className={labelClass}>Inventory item *</label>
                        <select
                          required
                          value={line.item_id}
                          onChange={(event) =>
                            updateLine(index, "item_id", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">Select inventory item</option>
                          {items.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : (
                      <div>
                        <label className={labelClass}>Prepared food name *</label>
                        <input
                          required
                          maxLength={150}
                          value={line.food_name}
                          onChange={(event) =>
                            updateLine(index, "food_name", event.target.value)
                          }
                          placeholder="Example: Vegetable biryani"
                          className={inputClass}
                        />
                      </div>
                    )}

                    {line.waste_type === "PREPARED_FOOD" && (
                      <div>
                        <label className={labelClass}>Related menu (optional)</label>
                        <select
                          value={line.menu_id}
                          onChange={(event) =>
                            updateLine(index, "menu_id", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">No related menu</option>
                          {menus.map((menu) => (
                            <option key={menu.id} value={menu.id}>
                              {menu.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className={labelClass}>Unit *</label>
                        <select
                          required
                          value={line.unit_id}
                          onChange={(event) =>
                            updateLine(index, "unit_id", event.target.value)
                          }
                          className={inputClass}
                        >
                          <option value="">Select unit</option>
                          {units.map((unit) => (
                            <option key={unit.id} value={unit.id}>
                              {unit.name}
                              {unit.symbol ? ` (${unit.symbol})` : ""}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className={labelClass}>Quantity *</label>
                        <input
                          type="number"
                          required
                          min="0.001"
                          step="0.001"
                          value={line.quantity}
                          onChange={(event) =>
                            updateLine(index, "quantity", event.target.value)
                          }
                          placeholder="Example: 2.500"
                          className={inputClass}
                        />
                      </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className={labelClass}>Waste stage *</label>
                        <select
                          required
                          value={line.waste_stage}
                          onChange={(event) =>
                            updateLine(index, "waste_stage", event.target.value)
                          }
                          className={inputClass}
                        >
                          {stages.map((stage) => (
                            <option key={stage.value} value={stage.value}>
                              {stage.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className={labelClass}>Waste reason *</label>
                        <select
                          required
                          value={line.waste_reason}
                          onChange={(event) =>
                            updateLine(index, "waste_reason", event.target.value)
                          }
                          className={inputClass}
                        >
                          {reasons.map((reason) => (
                            <option key={reason.value} value={reason.value}>
                              {reason.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className={labelClass}>
                        Estimated cost (₹) *
                      </label>
                      <input
                        type="number"
                        required
                        min="0"
                        step="0.01"
                        value={line.estimated_cost}
                        onChange={(event) =>
                          updateLine(index, "estimated_cost", event.target.value)
                        }
                        className={inputClass}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div>
                <label className={labelClass}>Notes</label>
                <textarea
                  rows={3}
                  maxLength={2000}
                  value={form.notes}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                  placeholder="Additional details about this waste record..."
                  className={inputClass}
                />
              </div>

              {error && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                >
                  {error}
                </div>
              )}

              <div className="flex flex-col-reverse justify-end gap-3 border-t border-slate-200 pt-4 sm:flex-row">
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving
                    ? "Saving..."
                    : editingId !== null
                      ? "Update Record"
                      : "Save Waste Record"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
