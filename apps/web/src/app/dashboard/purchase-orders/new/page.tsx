"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ClipboardList } from "lucide-react";

import { api } from "@/lib/api/client";
import { PURCHASE_ORDERS_ENDPOINT } from "@/lib/api/endpoints";
import { orderPayload, type OrderDraft } from "@/lib/orderForm";
import type { OrderDetail } from "@/lib/purchaseOrders";
import OrderForm, { emptyOrderDraft } from "@/components/orders/OrderForm";
import PageHeader from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";

export default function NewPurchaseOrderPage() {
  const router = useRouter();
  const toast = useToast();
  // Next.js keeps this page (hidden) after navigating away, with its state.
  // A saved order must not leave its values behind for the next visit, so
  // the form is started afresh as soon as the order is saved.
  const [formKey, setFormKey] = useState(0);

  async function create(draft: OrderDraft) {
    const order = await api.post<OrderDetail>(PURCHASE_ORDERS_ENDPOINT, orderPayload(draft));
    toast.success(`Draft order ${order.order_number} saved.`);
    setFormKey((key) => key + 1);
    router.push(`/dashboard/purchase-orders/${order.id}`);
  }

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={ClipboardList}
        title="New purchase order"
        description="Choose the supplier and the items and quantities to order. The order is saved as a draft; place it once it has been sent to the supplier."
        actions={
          <Link
            href="/dashboard/purchase-orders"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            <ArrowLeft size={15} aria-hidden />
            All orders
          </Link>
        }
      />
      <OrderForm
        key={formKey}
        initial={emptyOrderDraft()}
        submitLabel="Save draft order"
        cancelHref="/dashboard/purchase-orders"
        onSubmit={create}
      />
    </div>
  );
}
