import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Meal Sessions",
  description: "Configure the daily meal sessions served on campus.",
  endpoint: ENDPOINTS.mealSessions,
  fields: [
    { name: "name", label: "Session name", required: true, placeholder: "Breakfast" },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Session" },
  ],
};

export default function MealSessionsPage() {
  return <ResourcePage config={config} />;
}
