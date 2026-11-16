const PATH_PERMISSIONS: Record<string, string> = {
  "/dashboard/categories": "inventory.read",
  "/dashboard/units": "inventory.read",
  "/dashboard/unit-conversions": "inventory.read",
  "/dashboard/items": "inventory.read",
  "/dashboard/suppliers": "inventory.read",

  "/dashboard/meal-sessions": "menu.read",
  "/dashboard/menus": "menu.read",
  "/dashboard/menu-main-items": "menu.read",

  "/dashboard/waste-tracking": "waste_tracking.read",
};

export function canAccessPath(
  role: string,
  pathname: string,
  permissions: string[]
): boolean {
  if (pathname === "/dashboard") {
    return true;
  }

  if (
    pathname === "/dashboard/staff" ||
    pathname.startsWith("/dashboard/staff/")
  ) {
    return role === "ADMIN";
  }

  if (role === "ADMIN") {
    return true;
  }

  const matchingPath = Object.keys(PATH_PERMISSIONS).find(
    (path) =>
      pathname === path || pathname.startsWith(`${path}/`)
  );

  if (!matchingPath) {
    return false;
  }

  return permissions.includes(PATH_PERMISSIONS[matchingPath]);
}
