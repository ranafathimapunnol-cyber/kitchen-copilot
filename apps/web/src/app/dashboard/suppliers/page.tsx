import ResourcePage from "@/components/shared/ResourcePage";
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

// Access is checked by DashboardShell (canAccessPath: inventory.read), and
// each action button follows the user's permissions in ResourcePage. ADMIN
// and KITCHEN_MANAGER can manage suppliers; permanent delete stays
// ADMIN-only. The API enforces all of this independently.
export default function SuppliersPage() {
  return <ResourcePage config={config} />;
}
