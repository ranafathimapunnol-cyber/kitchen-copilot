import Badge, { type BadgeTone } from "@/components/ui/Badge";
import {
  DELIVERY_STATUS_LABELS,
  MEAL_LINK_LABELS,
  ORDER_STATUS_LABELS,
  RECEIVING_LABELS,
  REPORT_STATUS_LABELS,
  type DeliveryStatus,
  type MealLinkState,
  type OutsourcedStatus,
  type ReceivingStatus,
} from "@/lib/outsourced";

const ORDER_TONES: Record<OutsourcedStatus, BadgeTone> = { DRAFT: "warning", ORDERED: "brand", CANCELLED: "neutral" };
const DELIVERY_TONES: Record<DeliveryStatus, BadgeTone> = { DRAFT: "warning", CONFIRMED: "success", CANCELLED: "neutral" };
const RECEIVING_TONES: Record<ReceivingStatus, BadgeTone> = {
  NOT_RECEIVED: "neutral",
  PARTLY_RECEIVED: "warning",
  RECEIVED: "success",
};
const LINK_TONES: Record<MealLinkState, BadgeTone> = {
  ADDED: "success",
  PENDING_NO_RECORD: "warning",
  PENDING_CLOSED: "danger",
  NOT_CONFIRMED: "neutral",
  NOTHING_ACCEPTED: "neutral",
};

export function OutsourcedStatusBadge({ status }: { status: OutsourcedStatus }) {
  return <Badge tone={ORDER_TONES[status] ?? "neutral"} dot>{ORDER_STATUS_LABELS[status] ?? status}</Badge>;
}

export function DeliveryStatusBadge({ status }: { status: DeliveryStatus }) {
  return <Badge tone={DELIVERY_TONES[status] ?? "neutral"} dot>{DELIVERY_STATUS_LABELS[status] ?? status}</Badge>;
}

export function OutsourcedReceivingBadge({ status }: { status: ReceivingStatus }) {
  return <Badge tone={RECEIVING_TONES[status] ?? "neutral"}>{RECEIVING_LABELS[status] ?? status}</Badge>;
}

export function MealLinkBadge({ state }: { state: MealLinkState }) {
  return <Badge tone={LINK_TONES[state] ?? "neutral"}>{MEAL_LINK_LABELS[state] ?? state}</Badge>;
}

export function ReportStatusBadge({ status }: { status: string }) {
  const tone: BadgeTone = status === "RECONCILED" ? "success" : status === "NOT_DELIVERED" || status === "ALL_REJECTED" ? "neutral" : "warning";
  return <Badge tone={tone}>{REPORT_STATUS_LABELS[status] ?? status}</Badge>;
}
