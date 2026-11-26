"use client";

import { CheckCheck } from "lucide-react";

import Button from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import {
  formatQuantity,
  updateLineInput,
  type LineCheck,
  type LineInput,
} from "@/lib/receiptMath";
import { canViewOrders } from "@/lib/purchaseOrders";
import type { ReceivingLine } from "@/lib/receipts";
import { useAuthorization } from "@/components/layout/AuthorizationContext";

export type EditorLine = {
  line: ReceivingLine;
  /** What this receipt may still take on the line (for an existing draft,
   * its own quantity is added back). */
  remaining: string;
  input: LineInput;
};

function QuantityInput({
  label,
  value,
  invalid,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  invalid: boolean;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <TextInput
      aria-label={label}
      inputMode="decimal"
      autoComplete="off"
      placeholder="0"
      className="w-24 text-right tabular-nums"
      value={value}
      disabled={disabled}
      aria-invalid={invalid}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/**
 * The quantity grid for a receipt: for each bill line, what was billed,
 * already received and held in drafts, and the received / accepted /
 * rejected quantities of this delivery. Lines left at 0 received are not
 * part of the receipt.
 */
export default function ReceiptLinesEditor({
  lines,
  checks,
  disabled,
  onChange,
}: {
  lines: EditorLine[];
  checks: LineCheck[];
  disabled?: boolean;
  onChange: (index: number, input: LineInput) => void;
}) {
  const { role, permissions } = useAuthorization();
  // Ordered quantities come from purchase orders: never shown to STAFF.
  const showOrdered = canViewOrders(role, permissions) && lines.some(({ line }) => line.ordered_quantity);
  return (
    <Table minWidth={showOrdered ? "1080px" : "980px"}>
      <THead>
        <tr>
          <TH>Item</TH>
          {showOrdered && <TH align="right">Ordered</TH>}
          <TH align="right">Billed</TH>
          <TH align="right">Received so far</TH>
          <TH align="right">In other drafts</TH>
          <TH align="right">Left to receive</TH>
          <TH align="right">Received now</TH>
          <TH align="right">Accepted</TH>
          <TH align="right">Rejected</TH>
        </tr>
      </THead>
      <TBody>
        {lines.map(({ line, remaining, input }, index) => {
          const check = checks[index];
          const unit = line.unit_symbol ?? "";
          // Rejected follows received − accepted until the user types one.
          const update = (patch: Partial<LineInput>) => onChange(index, updateLineInput(input, patch));
          const nothingLeft = formatQuantity(remaining) === "0";
          return (
            <TR key={line.purchase_item_id}>
              <TD>
                <div className="font-medium text-slate-900">{line.item_name ?? `Line ${line.purchase_item_id}`}</div>
                {line.category_name && <div className="text-xs text-slate-500">{line.category_name}</div>}
                {check?.error && (
                  <p role="alert" className="mt-1 text-xs font-medium text-red-600" data-line-error>
                    {check.error}
                  </p>
                )}
              </TD>
              {showOrdered && (
                <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">
                  {line.ordered_quantity ? `${formatQuantity(line.ordered_quantity)} ${unit}` : "—"}
                </TD>
              )}
              <TD align="right" className="whitespace-nowrap tabular-nums">
                {formatQuantity(line.billed_quantity)} {unit}
              </TD>
              <TD align="right" className="whitespace-nowrap tabular-nums">
                {formatQuantity(line.received_quantity)} {unit}
              </TD>
              <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">
                {formatQuantity(line.in_draft_quantity)} {unit}
              </TD>
              <TD align="right" className="whitespace-nowrap tabular-nums font-medium text-slate-900">
                {formatQuantity(remaining)} {unit}
                {!nothingLeft && !disabled && (
                  <div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="mt-1 h-7 px-2 text-xs"
                      icon={<CheckCheck size={13} aria-hidden />}
                      onClick={() =>
                        onChange(index, {
                          received: formatQuantity(remaining),
                          accepted: formatQuantity(remaining),
                          rejected: "0",
                        })
                      }
                    >
                      All arrived
                    </Button>
                  </div>
                )}
              </TD>
              <TD align="right">
                <QuantityInput
                  label={`Received now, ${line.item_name ?? "line"}`}
                  value={input.received}
                  invalid={Boolean(check?.error)}
                  disabled={disabled || (nothingLeft && !input.received)}
                  onChange={(value) => update({ received: value })}
                />
              </TD>
              <TD align="right">
                <QuantityInput
                  label={`Accepted, ${line.item_name ?? "line"}`}
                  value={input.accepted}
                  invalid={Boolean(check?.error)}
                  disabled={disabled || (nothingLeft && !input.received)}
                  onChange={(value) => update({ accepted: value })}
                />
              </TD>
              <TD align="right">
                <QuantityInput
                  label={`Rejected, ${line.item_name ?? "line"}`}
                  value={input.rejected}
                  invalid={Boolean(check?.error)}
                  disabled={disabled || (nothingLeft && !input.received)}
                  onChange={(value) => onChange(index, { ...input, rejected: value })}
                />
              </TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
