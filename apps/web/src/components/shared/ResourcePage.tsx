
"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { api } from "@/lib/api/client";
import type {
  FieldConfig,
  ResourceConfig,
  SelectOption,
} from "@/types";
import Button from "@/components/ui/Button";

type RecordItem = Record<string, unknown>;

function normalizeList(data: unknown): RecordItem[] {
  if (Array.isArray(data)) return data as RecordItem[];

  if (data && typeof data === "object") {
    const object = data as Record<string, unknown>;
    for (const key of ["items", "results", "data"]) {
      if (Array.isArray(object[key])) return object[key] as RecordItem[];
    }
  }

  return [];
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function ResourcePage({
  config,
}: {
  config: ResourceConfig;
}) {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [options, setOptions] = useState<Record<string, SelectOption[]>>({});
  const [form, setForm] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const list = await api.get<unknown>(config.endpoint);
      setRecords(normalizeList(list));

      const optionFields = config.fields.filter(
        (field) => field.optionsEndpoint,
      );

      const optionResults = await Promise.all(
        optionFields.map(async (field) => {
          const data = await api.get<unknown>(field.optionsEndpoint!);
          const rows = normalizeList(data);

          return [
            field.name,
            rows.map((row) => ({
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
      setError(err instanceof Error ? err.message : "Unable to load records.");
    } finally {
      setLoading(false);
    }
  }, [config]);

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

  const updateField = (name: string, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
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
          payload[field.name] = value === "" ? 0 : Number(value);
        } else if (field.type === "select") {
          payload[field.name] = value ? Number(value) : null;
        } else {
          payload[field.name] = value || null;
        }
      }

      await api.post(config.endpoint, payload);
      setForm({});
      setSuccess("Record created successfully.");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save record.");
    } finally {
      setSaving(false);
    }
  };

  const renderField = (field: FieldConfig) => {
    const common =
      "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100";

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
            onChange={(event) => updateField(field.name, event.target.value)}
          />
        ) : field.type === "select" ? (
          <select
            className={common}
            required={field.required}
            value={form[field.name] || ""}
            onChange={(event) => updateField(field.name, event.target.value)}
          >
            <option value="">Select {field.label.toLowerCase()}</option>
            {(options[field.name] || []).map((option) => (
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
            onChange={(event) => updateField(field.name, event.target.value)}
          />
        )}
      </label>
    );
  };

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

        <Button onClick={() => void loadData()} disabled={loading}>
          <RefreshCw size={16} className="mr-2" />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {success && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
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
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                    {config.fields.slice(0, 4).map((field) => (
                      <th key={field.name} className="px-3 py-3 font-semibold">
                        {field.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.map((record, index) => (
                    <tr
                      key={String(record.id ?? index)}
                      className="border-b border-slate-100 last:border-0"
                    >
                      {config.fields.slice(0, 4).map((field) => (
                        <td
                          key={field.name}
                          className="px-3 py-3 text-slate-700"
                        >
                          {displayValue(record[field.name])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Plus size={18} className="text-blue-700" />
            <h2 className="text-lg font-semibold text-slate-900">
              Add {config.title}
            </h2>
          </div>

          <form
            onSubmit={submit}
            className="space-y-4"
          >
            {config.fields.map(renderField)}

            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Create record"}
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
