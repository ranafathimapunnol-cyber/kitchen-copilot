import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Unit Conversions",
  description: "Define conversion factors between compatible measurement units.",
  endpoint: ENDPOINTS.unitConversions,
  fields: [
    {
      name: "from_unit_id",
      label: "From unit",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.units,
    },
    {
      name: "to_unit_id",
      label: "To unit",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.units,
    },
    {
      name: "factor",
      label: "Conversion factor",
      type: "number" as const,
      required: true,
      placeholder: "Example: 1000",
    },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "from_unit_id", label: "From unit", optionField: "from_unit_id" },
    { key: "to_unit_id", label: "To unit", optionField: "to_unit_id" },
    { key: "factor", label: "Factor" },
  ],
};

export default function UnitConversionsPage() {
  return <ResourcePage config={config} />;
}
