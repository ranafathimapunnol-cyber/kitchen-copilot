import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Items",
  description: "Maintain ingredients, their categories, units and minimum stock.",
  endpoint: ENDPOINTS.items,
  fields: [
    { name: "name", label: "Item name", required: true, placeholder: "Raw rice" },
    {
      name: "category_id",
      label: "Category",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.categories,
    },
    {
      name: "unit_id",
      label: "Standard unit",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.units,
    },
    {
      name: "minimum_stock",
      label: "Minimum stock",
      type: "number" as const,
      required: true,
      placeholder: "0",
    },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Item" },
    { key: "category_id", label: "Category ID" },
    { key: "standard_unit_id", label: "Standard unit ID" },
    { key: "minimum_stock", label: "Minimum stock" },
  ],
};

export default function ItemsPage() {
  return <ResourcePage config={config} />;
}
