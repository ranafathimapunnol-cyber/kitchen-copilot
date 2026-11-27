/** Platform (organisation-level, SUPER_ADMIN) API types and helpers — Stage 11. */

export const PLATFORM_API = "/api/platform";

export type PlatformUser = {
  id: number;
  full_name: string;
  email: string;
  role: "SUPER_ADMIN";
  organization_id: number | null;
  session_minutes: number;
  last_login_at: string | null;
};

export type ErpStatus = {
  kind: "ERP_HEADCOUNT";
  state: "NOT_CONFIGURED" | "DISABLED" | "AWAITING_CONTRACT";
  label: string;
  enabled: boolean;
  base_url: string | null;
  credential: "set" | "not set";
  timeout_seconds: number;
  max_retries: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_error: string | null;
  contract: "pending";
};

export type CampusUsers = { total: number; active: number; ADMIN: number; KITCHEN_MANAGER: number; STAFF: number };

export type CampusOperations = {
  stock: { items_tracked: number; below_minimum: number; out_of_stock: number };
  pending_adjustments: number;
  meals_awaiting_close: number;
  open_meal_records: number;
  draft_plans: number;
  outstanding_payables: string;
  open_bills: number;
};

/** Version tokens of the campus logo and photo (null = none). */
export type CampusMedia = { logo: string | null; photo: string | null; available: boolean };

export type CampusRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  organization_id: number | null;
  organization_name?: string | null;
  users: CampusUsers;
  purchases: { bill_count: number; total: string };
  last_activity_at: string | null;
  erp: ErpStatus;
  operations?: CampusOperations;
  media?: CampusMedia;
};

export type CampusDetail = CampusRow & {
  address: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  created_at: string | null;
  updated_at: string | null;
  deactivated_at: string | null;
  deactivation_reason: string | null;
  alerts?: Alert[];
  period?: Period;
};

export type Alert = { campus_id: number; campus_name: string; level: "critical" | "warning" | "info"; text: string };
export type Period = { date_from: string; date_to: string };

export type AuditRow = {
  id: number;
  occurred_at: string;
  actor_user_id: number | null;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: number | null;
  campus_id: number | null;
  outcome: "SUCCESS" | "FAILURE" | "DENIED";
  ip_address: string | null;
  details: Record<string, unknown>;
};

export type Overview = {
  period: Period;
  generated_at: string;
  totals: {
    campuses: number; active_campuses: number; inactive_campuses: number;
    users: number; active_users: number; admins: number; kitchen_managers: number; staff: number;
    purchases_total: string; bills: number; outstanding_payables: string;
    items_below_minimum: number; items_out_of_stock: number; erp_configured: number;
  };
  campuses: (CampusRow & { operations: CampusOperations })[];
  alerts: Alert[];
  activity: AuditRow[];
};

export type PlatformUserRow = {
  id: number; full_name: string; email: string; role: string; is_active: boolean;
  campus_id: number | null; campus_name: string | null; last_login_at: string | null;
};

export type HealthCheck = { key: string; label: string; state: "ok" | "warning" | "error" | "off" | "not_configured"; detail: string };

export const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Platform administrator",
  ADMIN: "Admin",
  KITCHEN_MANAGER: "Kitchen Manager",
  STAFF: "Staff",
};

export const ACTION_LABELS: Record<string, string> = {
  LOGIN: "Sign-in",
  LOGOUT: "Sign-out",
  CREATE: "Created",
  UPDATE: "Edited",
  ACTIVATE: "Activated",
  DEACTIVATE: "Deactivated",
  PROVISION_ADMIN: "Campus Admin invited",
  CONFIGURE_INTEGRATION: "Integration settings changed",
  ERP_SYNC: "ERP sync run",
};

/** "Hill Campus deactivated", "Sign-in failed (root@…)" — one readable line. */
export function auditSentence(row: AuditRow, campusNames: Record<number, string> = {}): string {
  const action = ACTION_LABELS[row.action] ?? row.action;
  const target = row.target_type === "CAMPUS" && row.campus_id
    ? campusNames[row.campus_id] ?? `campus #${row.campus_id}`
    : row.target_type === "PLATFORM_SESSION" ? "" : row.target_type.toLowerCase().replaceAll("_", " ");
  const outcome = row.outcome === "SUCCESS" ? "" : row.outcome === "DENIED" ? " (refused)" : " (failed)";
  return `${action}${target ? ` · ${target}` : ""}${outcome}`;
}

export function money(value: string | number): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .format(Number(value));
}

export const n = (value: number) => value.toLocaleString("en-IN");

/** First day of this month to today, as yyyy-mm-dd (local time). */
export function monthToDate(today = new Date()): Period {
  const pad = (v: number) => String(v).padStart(2, "0");
  const y = today.getFullYear();
  const m = pad(today.getMonth() + 1);
  return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${pad(today.getDate())}` };
}

export function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const ERP_STATE_TONE: Record<ErpStatus["state"], "neutral" | "warning" | "brand"> = {
  NOT_CONFIGURED: "neutral",
  DISABLED: "neutral",
  AWAITING_CONTRACT: "warning",
};

export const MEDIA_SPECS = {
  logo: { label: "Logo", hint: "Square works best. PNG, JPEG or WebP up to 5 MB; stored as PNG, at most 512 px, transparency kept." },
  photo: { label: "Campus photo", hint: "PNG, JPEG or WebP up to 5 MB; stored as JPEG, at most 1600 px. Location and camera details are removed." },
} as const;

export function mediaPath(campusId: number, kind: "logo" | "photo", version: string): string {
  return `${PLATFORM_API}/campuses/${campusId}/media/${kind}?v=${version}`;
}
