export const ENDPOINTS = {
  login: "/api/auth/login",
  csrf: "/api/auth/csrf",
  refresh: "/api/auth/refresh",
  logout: "/api/auth/logout",
  me: "/api/auth/me",

  categories: "/api/master/categories",
  units: "/api/master/units",
  items: "/api/master/items",
  suppliers: "/api/master/suppliers",
  mealSessions: "/api/master/meal-sessions",
  menus: "/api/master/menus",
} as const;
