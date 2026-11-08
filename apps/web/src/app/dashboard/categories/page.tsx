import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Categories",
  description: "Organize ingredients into manageable stock categories.",
  endpoint: ENDPOINTS.categories,
  fields: [
    { name: "name", label: "Category name", required: true, placeholder: "e.g. Vegetables" },
    { name: "description", label: "Description", type: "textarea" as const },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Category" },
    { key: "description", label: "Description" },
  ],
};

export default function CategoriesPage() {
  return <ResourcePage config={config} />;
}
