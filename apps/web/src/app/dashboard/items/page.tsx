import ItemsResourcePage from "@/components/items/ItemsResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Items",
  description:
    "Maintain ingredients, their categories, units and minimum stock. The item kind (raw, prepared or outsourced) is set by an Admin or Kitchen Manager with Classify.",
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
      name: "standard_unit_id",
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
    { key: "category_id", label: "Category", optionField: "category_id" },
    { key: "standard_unit_id", label: "Standard unit", optionField: "standard_unit_id" },
    { key: "minimum_stock", label: "Minimum stock" },
    {
      key: "item_kind",
      label: "Kind",
      labels: { RAW: "Raw", PREPARED: "Prepared", OUTSOURCED: "Outsourced" },
      emptyLabel: "Not classified",
    },
  ],
};

export default function ItemsPage() {
  return <ItemsResourcePage config={config} />;
}
