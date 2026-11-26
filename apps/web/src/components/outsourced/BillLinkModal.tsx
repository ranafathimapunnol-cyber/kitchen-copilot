"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import { outsourcedLineBillEndpoint } from "@/lib/api/endpoints";
import type { BillCandidate, OutsourcedOrderDetail, OutsourcedOrderLine } from "@/lib/outsourced";
import { errorMessage, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import { Spinner } from "@/components/ui/States";

/**
 * Link the supplier bill line that bills one order line (OUT01 criterion 6):
 * the order's supplier, the same item and the same unit (no conversion is
 * assumed, Q7). One bill line bills one order line. The bill stays the only
 * payable; the order's rate is the planned cost.
 */
export default function BillLinkModal({
  order,
  line,
  onClose,
  onSaved,
}: {
  order: OutsourcedOrderDetail;
  line: OutsourcedOrderLine;
  onClose: () => void;
  onSaved: (updated: OutsourcedOrderDetail) => void;
}) {
  const [candidates, setCandidates] = useState<BillCandidate[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get<{ items: BillCandidate[] }>(outsourcedLineBillEndpoint(line.id, "bill-candidates"))
      .then((response) => active && setCandidates(response.items))
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load the supplier's bill lines.")));
    return () => {
      active = false;
    };
  }, [line.id]);

  async function save() {
    if (chosen === null) {
      setError("Choose the bill line that bills this food.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      onSaved(await api.put<OutsourcedOrderDetail>(outsourcedLineBillEndpoint(line.id, "bill-line"), { purchase_item_id: chosen }));
    } catch (err: unknown) {
      setError(errorMessage(err, "The bill line could not be linked."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      size="lg"
      dismissible={!saving}
      onClose={() => (saving ? undefined : onClose())}
      title={`Link the bill for ${line.item_name}`}
      description={`Bill lines from ${order.supplier_name ?? "the supplier"} for ${line.item_name} that are not linked to another order. Ordered: ${plainQuantity(line.ordered_quantity)} ${line.unit_symbol ?? ""}.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button loading={saving} disabled={!candidates?.length} onClick={save}>Link bill line</Button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        {candidates === null && !error ? (
          <Spinner label="Loading bill lines" />
        ) : candidates && candidates.length === 0 ? (
          <p className="text-sm text-slate-600">
            No unlinked bill line from this supplier for this item. Enter the supplier&rsquo;s bill under Supplier Bills first.
          </p>
        ) : (
          <ul className="space-y-2" aria-label="Bill lines">
            {candidates?.map((candidate) => (
              <li key={candidate.purchase_item_id}>
                <label className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${candidate.same_unit ? "border-slate-200" : "border-slate-100 opacity-60"}`}>
                  <input type="radio" name="bill-line" className="mt-1" disabled={!candidate.same_unit || saving}
                    checked={chosen === candidate.purchase_item_id} onChange={() => setChosen(candidate.purchase_item_id)} />
                  <span className="min-w-0">
                    <span className="font-medium text-slate-900">{candidate.invoice_number}</span>
                    <span className="text-slate-500"> · {formatDay(candidate.purchase_date)}</span>
                    <span className="block text-slate-700">
                      {plainQuantity(candidate.quantity)} {candidate.unit_symbol} × {formatRupees(candidate.unit_rate)} = {formatRupees(candidate.line_total)}
                    </span>
                    {!candidate.same_unit && <span className="block text-xs text-amber-700">Different unit — cannot be linked (no conversion is assumed).</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
