# Stages 10, 11 and 12 — Implementation Notes

Implemented 26 November 2026. Stages 10 and 12: migration `c4d7e9a1f203`
(M7, additive), applied to the development database after a verified backup
(`~/kitchen-copilot-backups/pre-c4d7e9a1f203-20261126-210339`). Stage 11 is a
separate migration (`d5e8f0b2a314`, M1) that is **prepared but not applied**
— it needs its own authorization.
Statuses in `REQUIREMENTS-TRACEABILITY.md`; nothing here is ACCEPTED.

## Stage 10 — security, user accounts, audit viewer

- **Sign-in throttling (interim rule for Q19):** every attempt is recorded in
  `login_attempts` (no password stored). 5 failures for one email, or 30
  from one IP address, within 15 minutes → HTTP 429 with `Retry-After`.
  A refused attempt is not itself counted.
- **Sessions:** `users.sessions_revoked_at`; any token issued before it is
  refused (access and refresh). Set by "Sign out everywhere" (own account),
  by an Admin's "Sign out", by deactivation and by a role change.
- **User Accounts** (`/dashboard/users`, API `/api/admin/users`): ADMIN only,
  own campus only. Edit name; change Kitchen Manager ↔ Staff; deactivate and
  reactivate with a reason; sign out; single-use password reset link (the
  password is never shown); sign-in history. An Admin never changes their own
  role or status, no account becomes ADMIN here, and the campus keeps at
  least one active Admin. STAFF permissions are unchanged and stay on Staff
  Management.
- **Audit Log** (`/dashboard/audit`, API `/api/audit`): `audit.read`
  (ADMIN, KITCHEN_MANAGER), own campus, read-only, filters and paging. Money
  values in details are shown as "hidden" unless the reader holds
  `purchase_bill.read`.

## Stage 11 — platform (SUPER_ADMIN) — prepared, not applied

> **Superseded by `docs/PHASE-2-PLATFORM.md` (27 Nov 2026):** the platform is now
> built in the working tree (separate sign-in and app, platform audit, ERP
> adapter); M1 was extended and is still not applied. The text below is the
> earlier design.

Not in the working tree's API yet: migration `d5e8f0b2a314`, the platform
routes, `scripts/create_super_admin.py` and their 3 tests are held back until
M1 is authorized. The web screen `/dashboard/platform` exists but is reachable
only by a SUPER_ADMIN, and none can exist before M1. Design once applied:


- Fourth role `SUPER_ADMIN`: no campus (check `ck_user_campus_by_role`),
  every campus permission denied in the API, no campus screens. Manages
  organisations and campuses and invites each campus's Admin by emailed setup
  link (`/dashboard/platform`, API `/api/platform`). Campus user
  authorization stays with the campus ADMIN.
- Platform audit rows have no campus (`audit_logs.campus_id` NULL); campus
  screens never show them.
- First SUPER_ADMIN: `scripts/create_super_admin.py` (operator, needs SMTP).
  **Not run** on any database (and not in the working tree until M1).

## Stage 12 — Kitchen Copilot agent

Flow of one turn (`app/agent/engine.py`):

1. **Understand** (`app/agent/intent.py`): built-in rule reader; optional
   Gemini reader when enabled and configured (request text and the campus's
   session/menu/item names only), validated, with fallback to rules.
2. **Plan**: the steps are shown to the user ("How I worked on this").
3. **Retrieve** through registered tools only (`app/agent/tools.py`); each
   re-checks role and permission, is campus-scoped through the user, calls
   the existing tested application functions, and is recorded as a step.
4. **Explain** with the application's figures; links to the source screens.
5. **Propose** consequential actions as `PENDING` proposals:
   draft meal plan (`meal_plan.create`), draft purchase order per last
   supplier (`purchase_order.create`), stock adjustment *request*
   (`stock_count.create`; posting still needs the independent approver).
6. **Approve** (`app/agent/executor.py`): a person decides; the proposal is
   locked, must be pending and unexpired, the approver's role and permission
   are checked again, the action runs through the same application function
   as the normal screen (its own validation and audit), and the decision and
   result are audited. A second approval is refused (no duplicate effect).

The LLM never touches the database and never produces figures. With
`AGENT_ENABLED=false` (default) the API refuses agent requests and the screen
says Copilot is turned off; all other screens are unaffected.

**Deviation needing approval:** ADR-005 names a separate Flask Actions
service; this release executes approved actions in the API process with the
same ADR-010 contract. ADR-009's PostgreSQL JSON option is used for traces.

**Not available yet:** approved procedure documents (none supplied; the agent
says guidance is unavailable from approved sources); a live Gemini key (not
configured — the FakeLLM tests cover that path).

## Global Copilot panel (27 November 2026)

- **Everywhere:** a launcher at the bottom right of every campus dashboard
  screen opens a floating chat panel (full screen on phones). It is hidden on
  the full Copilot page, for SUPER_ADMIN, while the phone menu is open and
  when printing. One conversation is shared by the panel and the full page
  and kept across screens; the open conversation id is kept for the browser
  tab, so a reload reopens it.
- **Page context:** each question carries the screen being viewed
  (`page`, `/dashboard/...` paths only, validated by the API, recorded in the
  ASK audit row). It only focuses the answer and the suggested questions;
  access always comes from the user's own role and permissions.
- **New read-only job, "What needs attention":** reads the campus overview
  through the dashboard's own per-section permission checks (tool
  `operations_overview`, needs `dashboard.read`) and lists what needs action
  for the current screen's topic (stock, purchasing, meals and planning,
  outsourced food, spending and reports) or everything on the dashboard, with
  links to the screens where each item is handled. It writes nothing.
- **Shown in the panel:** the tools each answer used ("Checked: …"), the
  plan, proposal cards with Approve/Reject for people allowed to decide, an
  Approvals tab, and a badge on the launcher counting PENDING proposals this
  user may decide (refreshed every two minutes while the tab is visible).
  Approval rules are unchanged: Copilot only proposes; the approve and reject
  endpoints re-check the deciding person's role and permission.
- **Fixed with it:** a campus name containing a weekday or month (menu
  "Monday Lunch") no longer moves the date of a planning request.
- **Tests:** `tests/test_copilot_global.py` (17), `apps/web/tests/copilot.test.mjs`
  (3); browser check on a throwaway copy of the development data, 43/43 and
  5/5 with the assistant turned off.

## Review on realistic data (27 November 2026)

The three workflows were run through the HTTP API, with approval and
rejection, as ADMIN, KITCHEN_MANAGER and STAFF, against a throwaway copy
of the development database (no change to the development data). Defects
found and fixed:

- Dates written as day and month ("30 November", "Nov 30th", "30/11") and
  explicit periods ("1 November to 15 November") were not understood; a
  bare headcount in a planning request ("for 200") was ignored.
- A category or item named in a spending question ("spend on vegetables")
  was ignored and the whole campus was explained. The answer now covers
  that category or item (bill line totals) and says so.
- When a meal session had no menu, the sessions offered instead included
  sessions without menus too. With duplicate session names ("Breakfast" /
  "breakfast", open question C5) the reader picked the one without menus.
- Raw status codes ("not_bought_now") appeared in the drivers table.
- Asking the same question again queued an identical pending proposal;
  now the waiting one is shown again (same conversation) or named.
- An empty "movements" table was shown when there were no movements.
- The result of an approved action linked to a list, not to the new record.
- The Spending Analysis page ignored the period and filter in Copilot's
  "Open in Spending Analysis" link.

The external model still receives only session, menu and item names
(categories are matched locally).

## Tests

`services/api/tests/test_stage10_12.py` (30 tests after the 27 November
review; 3 more Stage 11 tests
held with M1); `apps/web/tests/access.test.mjs`. Full backend suite with
Stages 10–12 together: 767 passed. Stage 10+12 code: targeted suites 154
passed. M7 rehearsal on a throwaway PostgreSQL (14 of 14): empty database
and a copy of the development data — upgrade, downgrade (refused while agent
conversations exist), upgrade; every existing row unchanged; STAFF grants,
permissions and ledger triggers unchanged. M7 + M1 together rehearsed 18 of
18 (M1's downgrade is refused while SUPER_ADMIN rows exist).
