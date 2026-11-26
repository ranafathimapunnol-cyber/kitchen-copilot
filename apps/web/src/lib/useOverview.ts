"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import { DASHBOARD_OVERVIEW_ENDPOINT } from "@/lib/api/endpoints";
import type { DashboardOverview } from "@/lib/dashboard";

/**
 * The dashboard overview, shared by the dashboard page and the top bar's
 * notifications so one page view makes one request. A reload always asks
 * the API again; the cache only spares duplicate requests within 30 s.
 */
let cached: { at: number; data: DashboardOverview } | null = null;
let inflight: Promise<DashboardOverview> | null = null;
const listeners = new Set<(data: DashboardOverview) => void>();
const FRESH_MS = 30_000;

function fetchOverview(force: boolean): Promise<DashboardOverview> {
  if (!force && cached && Date.now() - cached.at < FRESH_MS) return Promise.resolve(cached.data);
  if (!force && inflight) return inflight;
  inflight = api.get<DashboardOverview>(DASHBOARD_OVERVIEW_ENDPOINT)
    .then((data) => {
      cached = { at: Date.now(), data };
      listeners.forEach((listener) => listener(data));
      return data;
    })
    .finally(() => { inflight = null; });
  return inflight;
}

/** Forget the cached overview (sign-out). */
export function clearOverviewCache() {
  cached = null;
}

export function useOverview(enabled: boolean) {
  const [data, setData] = useState<DashboardOverview | null>(cached?.data ?? null);
  const [error, setError] = useState<unknown>(null);
  // Loading is derived: a request is outstanding until its key is settled.
  const [requestKey, setRequestKey] = useState(0);
  const [settledKey, setSettledKey] = useState(-1);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const listener = (next: DashboardOverview) => { if (active) setData(next); };
    listeners.add(listener);
    fetchOverview(requestKey > 0)
      .then((result) => { if (active) { setData(result); setError(null); } })
      .catch((err: unknown) => { if (active) setError(err); })
      .finally(() => { if (active) setSettledKey(requestKey); });
    return () => { active = false; listeners.delete(listener); };
  }, [enabled, requestKey]);

  const reload = useCallback(() => setRequestKey((key) => key + 1), []);

  return { data, error, loading: enabled && settledKey !== requestKey, reload };
}
