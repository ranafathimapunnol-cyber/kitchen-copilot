/** Kitchen Copilot (Stage 12) API types. */

export type WorkflowId = "plan_procure" | "explain_spending" | "stock_difference" | "attention";

export type AgentStatus = {
  enabled: boolean;
  reader: "rules" | "gemini";
  external_model: string | null;
  procedures_loaded: number;
  workflows: Record<WorkflowId, boolean>;
  proposal_ttl_hours: number;
};

export type AgentBlock =
  | { type: "table"; title: string; columns: string[]; rows: string[][]; note?: string }
  | { type: "list"; title: string; items: string[] };

export type AgentPayload = {
  status?: "answered" | "needs_info" | "not_allowed" | "error";
  workflow?: string | null;
  plan?: string[];
  blocks?: AgentBlock[];
  choices?: { label: string; text: string }[];
  links?: { label: string; href: string }[];
  sources?: { source: string; title: string; excerpt: string }[];
  proposal_ids?: number[];
  reader?: string;
  notes?: string[];
  /** The screen the question was asked from. */
  page?: string | null;
  /** Tool calls of this turn (permission-checked reads). */
  tools?: { name: string; ok: boolean; ms: number }[];
};

export type AgentMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  payload: AgentPayload;
  created_at: string;
};

export type AgentProposal = {
  id: number;
  conversation_id: number;
  workflow: string;
  action_type: string;
  title: string;
  rationale: string;
  payload: Record<string, unknown>;
  status: "PENDING" | "EXECUTING" | "EXECUTED" | "FAILED" | "REJECTED" | "EXPIRED";
  required_permission: string;
  created_at: string;
  created_by_name: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  result: { entity?: string; id?: number; number?: string; href?: string };
  error: string | null;
  can_decide: boolean;
};

export type AgentStep = {
  id: number; message_id: number | null; seq: number; kind: string; name: string;
  input: unknown; output: unknown; ok: boolean; duration_ms: number; created_at: string;
};

export const WORKFLOW_LABELS: Record<string, string> = {
  plan_procure: "Plan and procure",
  explain_spending: "Explain spending",
  stock_difference: "Stock difference",
  attention: "What needs attention",
};

/** Readable names of the agent's tools (app/agent/tools.py). */
export const TOOL_LABELS: Record<string, string> = {
  meal_options: "Meal sessions and menus",
  plan_requirements: "Meal requirements",
  last_suppliers: "Recent suppliers",
  procedures: "Approved procedures",
  spending_comparison: "Spending comparison",
  operations_overview: "Operations overview",
  headcount_summary: "Headcount",
  find_item: "Item record",
  latest_count_line: "Latest stock count",
  item_movements: "Stock ledger",
  unposted_documents: "Unposted documents",
};

export type Suggestion = { text: string; workflow: WorkflowId };

/** The topic of a screen, for the panel's "Viewing …" line and suggestions. */
const PAGE_TOPICS: { prefixes: string[]; topic: string; suggestions: Suggestion[] }[] = [
  {
    prefixes: ["/dashboard/stock", "/dashboard/items", "/dashboard/opening-stock", "/dashboard/kitchen-issues", "/dashboard/waste-tracking"],
    topic: "stock",
    suggestions: [
      { text: "What needs attention on this screen?", workflow: "attention" },
      { text: "Investigate the latest stock count difference", workflow: "stock_difference" },
    ],
  },
  {
    prefixes: ["/dashboard/purchase-orders", "/dashboard/receipts", "/dashboard/supplier", "/dashboard/purchase-payment-report"],
    topic: "purchasing",
    suggestions: [
      { text: "What needs attention on this screen?", workflow: "attention" },
      { text: "Why did spending change this month?", workflow: "explain_spending" },
      { text: "Plan tomorrow's lunch and tell me what to buy", workflow: "plan_procure" },
    ],
  },
  {
    prefixes: ["/dashboard/meals", "/dashboard/meal-plans", "/dashboard/meal-sessions", "/dashboard/menus", "/dashboard/menu-main-items", "/dashboard/portion-standards", "/dashboard/outsourced-food"],
    topic: "meals and planning",
    suggestions: [
      { text: "What needs attention on this screen?", workflow: "attention" },
      { text: "Plan tomorrow's lunch for 450 people and tell me what to buy", workflow: "plan_procure" },
    ],
  },
  {
    prefixes: ["/dashboard/analytics", "/dashboard/reports"],
    topic: "spending and reports",
    suggestions: [
      { text: "Why did food spending go up this month compared with last month?", workflow: "explain_spending" },
      { text: "What needs attention on this screen?", workflow: "attention" },
    ],
  },
];

const GENERAL: Suggestion[] = [
  { text: "What needs my attention today?", workflow: "attention" },
  { text: "Plan tomorrow's lunch for 450 people and tell me what to buy", workflow: "plan_procure" },
  { text: "Why did spending change this month?", workflow: "explain_spending" },
  { text: "Today's rice count is below the system. Find out why.", workflow: "stock_difference" },
];

function topicOf(pathname: string) {
  return PAGE_TOPICS.find((t) => t.prefixes.some((p) => pathname === p || pathname.startsWith(p.endsWith("supplier") ? p : `${p}/`) || pathname.startsWith(`${p}-`)));
}

export function pageTopic(pathname: string): string | null {
  return topicOf(pathname)?.topic ?? null;
}

/** Questions to offer on a screen, limited to jobs this user may run. */
export function suggestionsFor(pathname: string, workflows: Partial<Record<WorkflowId, boolean>>): Suggestion[] {
  const list = topicOf(pathname)?.suggestions ?? GENERAL;
  return list.filter((s) => workflows[s.workflow]);
}

/** The path sent as page context (the API accepts /dashboard paths only). */
export function pageContext(pathname: string): string | null {
  return /^\/dashboard(\/[a-z0-9-]+){0,4}$/.test(pathname) ? pathname : null;
}

export const ACTION_LABELS: Record<string, string> = {
  CREATE_MEAL_PLAN_DRAFT: "Create draft meal plan",
  CREATE_PURCHASE_ORDER_DRAFT: "Create draft purchase order",
  RAISE_STOCK_ADJUSTMENT_REQUEST: "Raise stock adjustment request",
};

export const EXAMPLES = [
  { label: "Plan and procure", text: "Plan tomorrow's lunch for 450 people and tell me what we need to buy." },
  { label: "Explain spending", text: "Why did food spending go up this month compared with last month?" },
  { label: "Stock difference", text: "Today's rice count is below the system. Find out why and prepare an adjustment." },
];

/** Readable lines for a proposal's payload (what exactly will be created). */
export function proposalLines(p: AgentProposal): string[] {
  const d = p.payload as Record<string, unknown>;
  if (p.action_type === "CREATE_PURCHASE_ORDER_DRAFT") {
    const items = (d.items as { item_name: string; quantity: string; unit_symbol: string }[]) ?? [];
    return [`Supplier: ${d.supplier_name}`, ...items.map((i) => `${i.item_name}: ${i.quantity} ${i.unit_symbol}`),
      d.expected_date ? `Expected by ${d.expected_date}` : "No expected date"];
  }
  if (p.action_type === "CREATE_MEAL_PLAN_DRAFT") {
    return [`Date: ${d.plan_date}`, `Expected headcount: ${d.expected_headcount}`,
      `${((d.lines as unknown[]) ?? []).length} main item(s) with their approved standards`];
  }
  if (p.action_type === "RAISE_STOCK_ADJUSTMENT_REQUEST") {
    return [`Count: ${d.count_number}`, `${d.item_name}: ${d.difference} ${d.unit}`, `Reason: ${d.reason}`];
  }
  return [];
}
