"use client";

import Link from "next/link";

import { LEFTOVER_LABELS, type LeftoverClass } from "@/lib/meals";
import type { Comparison } from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

const CLASSES: LeftoverClass[] = ["RETAINED", "RETURNED_TO_SUPPLIER", "WASTED", "DISPOSED"];

/**
 * Planned vs actual (PLAN08, MEAL02 criterion 4) for a plan and the meal
 * record of the exact same date and meal session. Actual usage is the net
 * usage of the linked kitchen issues (at closing, once the record is
 * closed); carried retained food is shown apart from prepared output.
 */
export default function PlanComparison({ comparison, showPlanLink = false }: { comparison: Comparison; showPlanLink?: boolean }) {
  const { headcounts } = comparison;
  return (
    <div className="space-y-4">
      {showPlanLink && (
        <p className="text-sm text-slate-700">
          Plan{" "}
          <Link href={`/dashboard/meal-plans/${comparison.plan.id}`} className="font-semibold text-brand-700 hover:underline">
            {comparison.plan.plan_number}
          </Link>{" "}
          · {comparison.plan.status.toLowerCase()} · {comparison.plan.calculation === "SNAPSHOT" ? "figures as approved" : "live draft figures"}
        </p>
      )}
      {comparison.record_note && <Alert tone="info">{comparison.record_note}</Alert>}
      {headcounts && (
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div><dt className="text-xs font-medium text-slate-500">Planned headcount</dt><dd className="text-sm font-semibold text-slate-900">{headcounts.plan_expected}</dd></div>
          <div><dt className="text-xs font-medium text-slate-500">Expected on the meal record</dt><dd className="text-sm font-semibold text-slate-900">{headcounts.record_expected}</dd></div>
          <div><dt className="text-xs font-medium text-slate-500">Actually served</dt><dd className="text-sm font-semibold text-slate-900">{headcounts.record_actual ?? "Not recorded"}</dd></div>
        </dl>
      )}
      {comparison.items.length > 0 && (
        <Table minWidth="820px">
          <THead>
            <tr>
              <TH>Item</TH>
              <TH align="right">Planned</TH>
              <TH align="right">Actual net usage</TH>
              <TH align="right">Difference</TH>
              <TH align="right">Planned per person</TH>
              <TH align="right">Actual per person</TH>
            </tr>
          </THead>
          <TBody>
            {comparison.items.map((row) => (
              <TR key={row.item_id}>
                <TD>
                  {row.item_name}
                  {!row.planned && <div><Badge tone="warning">used, not planned</Badge></div>}
                </TD>
                <TD align="right">{row.planned_quantity ? `${plainQuantity(row.planned_quantity)} ${row.unit_symbol}` : "—"}</TD>
                <TD align="right">{row.actual_net_quantity ? `${plainQuantity(row.actual_net_quantity)} ${row.unit_symbol}` : "—"}</TD>
                <TD align="right" className="font-semibold">{row.difference ? `${plainQuantity(row.difference)} ${row.unit_symbol}` : "—"}</TD>
                <TD align="right">{row.planned_per_person ? `${row.planned_per_person} ${row.unit_symbol}` : "—"}</TD>
                <TD align="right">{row.actual_per_person ? `${row.actual_per_person} ${row.unit_symbol}` : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {comparison.dishes.length > 0 && (
        <Table minWidth="920px">
          <THead>
            <tr>
              <TH>Dish</TH>
              <TH align="right">Prepared</TH>
              <TH align="right">Carried in</TH>
              <TH align="right">Received (outsourced)</TH>
              <TH align="right">Distributed</TH>
              <TH>Leftovers</TH>
            </tr>
          </THead>
          <TBody>
            {comparison.dishes.map((dish, index) => (
              <TR key={`${dish.dish_name}-${index}`}>
                <TD>{dish.dish_name}</TD>
                <TD align="right">{dish.kind === "PREPARED" ? `${plainQuantity(dish.prepared_quantity)} ${dish.unit_symbol}` : "—"}</TD>
                <TD align="right">{dish.kind === "CARRIED" ? `${plainQuantity(dish.carried_quantity)} ${dish.unit_symbol}` : "—"}</TD>
                <TD align="right">{dish.kind === "RECEIVED" ? `${plainQuantity(dish.received_quantity)} ${dish.unit_symbol}` : "—"}</TD>
                <TD align="right">{dish.distributed_quantity ? `${plainQuantity(dish.distributed_quantity)} ${dish.unit_symbol}` : "—"}</TD>
                <TD>
                  {CLASSES.filter((c) => dish.leftovers[c]).map((c) => `${LEFTOVER_LABELS[c]} ${plainQuantity(dish.leftovers[c])} ${dish.unit_symbol}`).join(" · ") || "—"}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <ul className="list-disc space-y-0.5 pl-5 text-xs text-slate-500">
        {comparison.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </div>
  );
}
