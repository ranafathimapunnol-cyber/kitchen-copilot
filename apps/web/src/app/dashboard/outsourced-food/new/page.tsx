"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Soup } from "lucide-react";

import { api } from "@/lib/api/client";
import { OUTSOURCED_ORDERS_ENDPOINT } from "@/lib/api/endpoints";
import type { OutsourcedOrderDetail } from "@/lib/outsourced";
import { orderPayload, type OrderDraft } from "@/lib/outsourcedMath";
import OutsourcedOrderForm from "@/components/outsourced/OutsourcedOrderForm";
import PageHeader from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";

/** ADMIN and KITCHEN_MANAGER only (canAccessPath and the API). */
export default function NewOutsourcedOrderPage() {
  const router = useRouter();
  const toast = useToast();
  // A saved order must not leave its values behind for the next visit.
  const [formKey, setFormKey] = useState(0);

  async function create(draft: OrderDraft) {
    const order = await api.post<OutsourcedOrderDetail>(OUTSOURCED_ORDERS_ENDPOINT, orderPayload(draft));
    toast.success(`Draft ${order.order_number} saved.`);
    setFormKey((key) => key + 1);
    router.push(`/dashboard/outsourced-food/${order.id}`);
  }

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Operations"
        icon={Soup}
        title="New outsourced order"
        description="The meal (date and exact session), the supplier and the food ordered with quantities and rates. Saved as a draft; mark it ordered once it has been sent to the supplier."
        actions={
          <Link
            href="/dashboard/outsourced-food"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            <ArrowLeft size={15} aria-hidden />
            All orders
          </Link>
        }
      />
      <OutsourcedOrderForm key={formKey} initial={null} submitLabel="Save draft order" cancelHref="/dashboard/outsourced-food" onSubmit={create} />
    </div>
  );
}
