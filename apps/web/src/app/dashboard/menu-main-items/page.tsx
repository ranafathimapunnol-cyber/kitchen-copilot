import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Menu Main Items",
  description: "Assign items and quantities to each menu.",
  // Stage 6, decision 6-2: these rows are kept unchanged and are not used by
  // meal planning; planning uses approved, versioned portion standards.
  notice:
    "Not used by planning. Meal plans use approved portion standards (Menu Planning → Portion Standards). Copy these quantities there as drafts; each draft needs approval.",
  endpoint: ENDPOINTS.menuMainItems,
  fields: [
    {
      name: "menu_id",
      label: "Menu",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.menus,
    },
    {
      name: "item_id",
      label: "Item",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.items,
      searchable: true,
    },
    {
      name: "quantity_per_person",
      label: "Quantity per person",
      type: "number" as const,
      required: true,
      placeholder: "Example: 0.25",
    },
    {
      name: "unit_id",
      label: "Unit",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.units,
    },
  ],
  columns: [
    { key: "menu_id", label: "Menu", optionField: "menu_id" },
    { key: "item_id", label: "Item", optionField: "item_id" },
    { key: "quantity_per_person", label: "Quantity per person" },
    { key: "unit_id", label: "Unit", optionField: "unit_id" },
  ],
};

export default function MenuMainItemsPage() {
  return <ResourcePage config={config} />;
}
