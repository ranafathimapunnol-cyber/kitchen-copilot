import Badge, { type BadgeTone } from "@/components/ui/Badge";

const STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  UNPAID: { label: "Unpaid", tone: "danger" },
  PARTIALLY_PAID: { label: "Partly paid", tone: "warning" },
  PAID: { label: "Paid", tone: "success" },
  // Paid beyond the bill total: needs attention, not a success state.
  OVERPAID: { label: "Overpaid", tone: "brand" },
};

/** A bill's payment status. The label carries the meaning, not colour. */
export default function PaymentStatusBadge({ status }: { status: string }) {
  const entry = STATUS[status] ?? { label: status, tone: "neutral" as const };

  return (
    <Badge tone={entry.tone} dot>
      {entry.label}
    </Badge>
  );
}
