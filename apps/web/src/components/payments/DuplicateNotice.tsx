"use client";

import { useState } from "react";
import { CheckCircle2, TriangleAlert } from "lucide-react";

import { api } from "@/lib/api/client";
import { duplicateReviewEndpoint } from "@/lib/api/endpoints";
import {
  errorMessage,
  formatDateTime,
  formatDay,
  formatRupees,
  type DuplicateStatus,
} from "@/lib/payments";
import Button from "@/components/ui/Button";
import { Field, TextArea } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";

/**
 * A bill's possible-duplicate status (PUR01): the similar invoices from the
 * same supplier, and either the review that cleared it or, for a user who
 * may review, a way to mark it "not a duplicate" with a note.
 */
export default function DuplicateNotice({
  purchaseId,
  status,
  canReview,
  onReviewed,
}: {
  purchaseId: number;
  status: DuplicateStatus;
  canReview: boolean;
  onReviewed: (status: DuplicateStatus) => void;
}) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  if (status.possible_duplicates.length === 0) return null;

  const similar = (
    <ul className="mt-1 space-y-0.5">
      {status.possible_duplicates.map((bill) => (
        <li key={bill.purchase_id}>
          <span className="font-medium">{bill.invoice_number}</span> · {formatDay(bill.purchase_date)} ·{" "}
          {formatRupees(bill.grand_total)}
        </li>
      ))}
    </ul>
  );

  if (status.duplicate_review) {
    const review = status.duplicate_review;
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900" data-duplicate-reviewed>
        <p className="flex items-center gap-2 font-semibold">
          <CheckCircle2 size={15} aria-hidden /> Reviewed: not a duplicate
        </p>
        <p className="mt-1">
          {review.reviewed_by_name ?? "A reviewer"} · {formatDateTime(review.reviewed_at)}
          {review.note && ` · “${review.note}”`}
        </p>
        <div className="mt-1 text-emerald-800">Similar invoices from this supplier:{similar}</div>
      </div>
    );
  }

  function review() {
    if (!note.trim()) {
      setError("Explain why this is not a duplicate.");
      return;
    }
    setSaving(true);
    setError("");
    api
      .post<DuplicateStatus>(duplicateReviewEndpoint(purchaseId), { note: note.trim() })
      .then((next) => {
        toast.success("Marked as not a duplicate.");
        onReviewed(next);
      })
      .catch((err: unknown) => setError(errorMessage(err, "The review could not be saved.")))
      .finally(() => setSaving(false));
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-duplicate-flag>
      <p className="flex items-center gap-2 font-semibold">
        <TriangleAlert size={15} aria-hidden /> Possible duplicate invoice
      </p>
      <div className="mt-1">
        This supplier has invoice numbers that match once case, spaces and punctuation are ignored:
        {similar}
      </div>
      {canReview && (
        <div className="mt-3 space-y-2">
          <Field label="Review note" error={error}>
            {({ id, describedBy }) => (
              <TextArea
                id={id}
                rows={2}
                maxLength={500}
                aria-describedby={describedBy}
                value={note}
                disabled={saving}
                placeholder="e.g. Separate delivery, confirmed with the supplier"
                onChange={(event) => setNote(event.target.value)}
              />
            )}
          </Field>
          <Button size="sm" variant="secondary" loading={saving} onClick={review}>
            Mark as not a duplicate
          </Button>
        </div>
      )}
    </div>
  );
}
