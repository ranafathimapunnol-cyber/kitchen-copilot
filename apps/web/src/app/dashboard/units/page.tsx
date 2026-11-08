import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Units",
  description: "Define the measurement units used for kitchen items.",
  endpoint: ENDPOINTS.units,
  fields: [
    { name: "name", label: "Unit name", required: true, placeholder: "Kilogram" },
    { name: "symbol", label: "Symbol", required: true, placeholder: "kg" },
    { name: "dimension", label: "Dimension", required: true, placeholder: "weight" },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Unit" },
    { key: "symbol", label: "Symbol" },
    { key: "dimension", label: "Dimension" },
  ],
};

export default function UnitsPage() {
  return <ResourcePage config={config} />;
}
