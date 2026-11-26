import Badge, { type BadgeTone } from "@/components/ui/Badge";
import {
  ORDER_STATUS_LABELS,
  RECEIVING_LABELS,
  type OrderStatus,
  type ReceivingState,
} from "@/lib/purchaseOrders";

const STATUS_TONES: Record<OrderStatus, BadgeTone> = {
  DRAFT: "warning",
  PLACED: "brand",
  CLOSED: "success",
  CANCELLED: "neutral",
};

const RECEIVING_TONES: Record<ReceivingState, BadgeTone> = {
  NOT_RECEIVED: "neutral",
  PARTLY_RECEIVED: "warning",
  RECEIVED: "success",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return (
    <Badge tone={STATUS_TONES[status] ?? "neutral"} dot>
      {ORDER_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

export function ReceivingBadge({ state }: { state: ReceivingState }) {
  return <Badge tone={RECEIVING_TONES[state] ?? "neutral"}>{RECEIVING_LABELS[state] ?? state}</Badge>;
}
