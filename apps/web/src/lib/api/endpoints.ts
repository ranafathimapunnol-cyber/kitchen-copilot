export const ENDPOINTS = {
  login: "/api/auth/login",
  csrf: "/api/auth/csrf",
  refresh: "/api/auth/refresh",
  logout: "/api/auth/logout",
  me: "/api/auth/me",

  createUser: "/api/auth/users",

  authorizationMe: "/api/authorization/me",
  authorizationModules: "/api/authorization/modules",
  staff: "/api/authorization/staff",

  categories: "/api/master/categories",
  units: "/api/master/units",
  items: "/api/master/items",
  suppliers: "/api/master/suppliers",
  mealSessions: "/api/master/meal-sessions",
  menus: "/api/master/menus",
  unitConversions: "/api/master/unit-conversions",
  menuMainItems: "/api/master/menu-main-items",

  wasteRecords: "/api/waste/records",
} as const;
