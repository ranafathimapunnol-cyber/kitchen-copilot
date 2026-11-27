"use client";

import { RefreshCw } from "lucide-react";

import { formatDateTime } from "@/lib/payments";
import { PLATFORM_API, type HealthCheck } from "@/lib/platform";
import Button from "@/components/ui/Button";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { HealthBadge, PlatformHeader, usePlatformGet } from "@/components/platform/parts";

/** System and integration health. No secret, key or connection string is shown. */
export default function HealthPage() {
  const { data, error, loading, reload } = usePlatformGet<{ checked_at: string; checks: HealthCheck[] }>(`${PLATFORM_API}/health`);
  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="System health"
        description="Availability and configuration of the services Kitchen Copilot depends on. Secrets are never shown."
        actions={<Button variant="secondary" icon={<RefreshCw size={15} />} loading={loading} onClick={reload}>Check again</Button>} />
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={6} /> : (
        <>
          <ul className="grid gap-3 md:grid-cols-2" data-health>
            {data.checks.map((c) => (
              <li key={c.key} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4" data-check={c.key}>
                <div className="min-w-0"><p className="font-semibold text-slate-900">{c.label}</p><p className="mt-1 text-sm text-slate-600">{c.detail}</p></div>
                <HealthBadge state={c.state} />
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-500">Checked {formatDateTime(data.checked_at)}.</p>
        </>
      )}
    </div>
  );
}
