"use client";

import { useCallback, useEffect, useState } from "react";
import type { ElementType, ReactNode } from "react";

import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/payments";
import type { ErpStatus, HealthCheck, Period } from "@/lib/platform";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { cn } from "@/components/ui/cn";

/** GET a platform endpoint; reloads when the path changes. */
export function usePlatformGet<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for this request
    setLoading(true);
    api.get<T>(path)
      .then((d) => { if (active) { setData(d); setError(""); } })
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load.")))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [path, tick]);

  return { data, error, loading, reload };
}

/** Editorial page title: eyebrow, large heading, one-line purpose, actions. */
export function PlatformHeader({ eyebrow, title, description, actions }: {
  eyebrow: string; title: string; description?: ReactNode; actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold tracking-[0.16em] text-slate-500 uppercase">{eyebrow}</p>
        <h1 className="mt-1 text-[1.9rem] leading-tight font-semibold tracking-tight text-slate-900 sm:text-[2.3rem]">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Kpi({ label, value, note, icon: Icon, tone = "neutral" }: {
  label: string; value: string; note?: string; icon?: ElementType; tone?: "neutral" | "warning" | "accent";
}) {
  return (
    <div className={cn("rounded-2xl border bg-white p-4 sm:p-5", tone === "warning" ? "border-amber-200" : "border-slate-200")} data-kpi={label}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12.5px] font-medium text-slate-500">{label}</p>
        {Icon && <Icon size={16} aria-hidden className={tone === "accent" ? "text-brand-600" : tone === "warning" ? "text-amber-600" : "text-slate-400"} />}
      </div>
      <p className="mt-2 text-[1.7rem] leading-none font-semibold tracking-tight text-slate-900 tabular-nums">{value}</p>
      {note && <p className="mt-2 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

/** Date range (and optional campus) filter; applies on submit. */
export function PeriodFilter({ value, onChange, campuses, campusId, onCampusChange }: {
  value: Period; onChange: (p: Period) => void;
  campuses?: { id: number; name: string }[]; campusId?: string; onCampusChange?: (id: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  const invalid = draft.date_from > draft.date_to;
  return (
    <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); if (!invalid) onChange(draft); }} aria-label="Filters">
      <Field label="From" className="w-40">
        {({ id }) => <TextInput id={id} type="date" value={draft.date_from} max={draft.date_to} onChange={(e) => setDraft({ ...draft, date_from: e.target.value })} />}
      </Field>
      <Field label="To" className="w-40">
        {({ id }) => <TextInput id={id} type="date" value={draft.date_to} min={draft.date_from} onChange={(e) => setDraft({ ...draft, date_to: e.target.value })} />}
      </Field>
      {campuses && onCampusChange && (
        <Field label="Campus" className="w-56">
          {({ id }) => (
            <SelectInput id={id} value={campusId ?? ""} onChange={(e) => onCampusChange(e.target.value)}>
              <option value="">All campuses</option>
              {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </SelectInput>
          )}
        </Field>
      )}
      <Button type="submit" variant="secondary" disabled={invalid}>Apply</Button>
      {invalid && <p className="w-full text-xs text-red-700">The start date must be on or before the end date.</p>}
    </form>
  );
}

export function ErpBadge({ erp }: { erp: Pick<ErpStatus, "state" | "label"> }) {
  return <Badge tone={erp.state === "AWAITING_CONTRACT" ? "warning" : "neutral"} dot>{erp.label}</Badge>;
}

export function ActiveBadge({ active }: { active: boolean }) {
  return <Badge tone={active ? "success" : "neutral"} dot>{active ? "Active" : "Deactivated"}</Badge>;
}

const HEALTH_TONE: Record<HealthCheck["state"], "success" | "warning" | "danger" | "neutral"> = {
  ok: "success", warning: "warning", error: "danger", off: "neutral", not_configured: "neutral",
};
const HEALTH_LABEL: Record<HealthCheck["state"], string> = {
  ok: "OK", warning: "Check", error: "Down", off: "Off", not_configured: "Not configured",
};

export function HealthBadge({ state }: { state: HealthCheck["state"] }) {
  return <Badge tone={HEALTH_TONE[state]} dot>{HEALTH_LABEL[state]}</Badge>;
}

export function Section({ title, description, action, children, className }: {
  title: string; description?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-slate-200 bg-white", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight text-slate-900">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
