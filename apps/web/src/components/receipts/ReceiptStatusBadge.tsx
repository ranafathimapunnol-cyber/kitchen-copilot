import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { RECEIPT_STATUS_LABELS, type ReceiptStatus } from "@/lib/receipts";

const TONES: Record<ReceiptStatus, BadgeTone> = {
  DRAFT: "warning",
  ACCEPTED: "success",
  CANCELLED: "neutral",
};

export default function ReceiptStatusBadge({ status }: { status: ReceiptStatus }) {
  return (
    <Badge tone={TONES[status] ?? "neutral"} dot>
      {RECEIPT_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
