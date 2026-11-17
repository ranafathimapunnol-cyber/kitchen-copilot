"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import ResourcePage from "@/components/shared/ResourcePage";
import { useAuth } from "@/hooks/useAuth";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Suppliers",
  description: "Maintain contact information for kitchen suppliers.",
  endpoint: ENDPOINTS.suppliers,
  fields: [
    { name: "name", label: "Supplier name", required: true, placeholder: "Supplier name" },
    { name: "phone", label: "Phone number", placeholder: "Phone number" },
    { name: "email", label: "Email", type: "email" as const, placeholder: "supplier@example.com" },
    { name: "address", label: "Address", type: "textarea" as const },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Supplier" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
  ],
};

export default function SuppliersPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const canAccessSuppliers =
    user && user.role === "ADMIN";

  useEffect(() => {
    if (!loading && user && !canAccessSuppliers) {
      router.replace("/dashboard");
    }
  }, [loading, user, canAccessSuppliers, router]);

  if (loading || !canAccessSuppliers) {
    return null;
  }

  return <ResourcePage config={config} />;
}
