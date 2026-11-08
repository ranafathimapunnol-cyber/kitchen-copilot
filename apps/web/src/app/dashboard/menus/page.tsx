import ResourcePage from "@/components/shared/ResourcePage";
import { ENDPOINTS } from "@/lib/api/endpoints";

const config = {
  title: "Menus",
  description: "Create menus and associate them with meal sessions.",
  endpoint: ENDPOINTS.menus,
  fields: [
    { name: "name", label: "Menu name", required: true, placeholder: "Monday Breakfast" },
    {
      name: "meal_session_id",
      label: "Meal session",
      type: "select" as const,
      required: true,
      optionsEndpoint: ENDPOINTS.mealSessions,
    },
  ],
  columns: [
    { key: "id", label: "ID" },
    { key: "name", label: "Menu" },
    { key: "meal_session_id", label: "Meal session ID" },
  ],
};

export default function MenusPage() {
  return <ResourcePage config={config} />;
}
