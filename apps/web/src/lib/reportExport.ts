/**
 * File names for report exports. The API names each file in its
 * Content-Disposition header; when a browser hides that header, the same
 * name is built here with the API's rule. No imports, so `node --test` can
 * run its tests directly.
 */

export type ExportFormat = "xlsx" | "pdf";

/** `attachment; filename="report.pdf"` → `report.pdf`. Null when absent. */
export function fileNameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const match = /filename="([^"]+)"/i.exec(header) ?? /filename=([^;\s]+)/i.exec(header);
  const name = match?.[1]?.trim();
  // Never let a server-supplied name point into a folder.
  return name ? name.replace(/[\\/]/g, "_") : null;
}

/** Same rule as the API's export_filename. */
export function exportFileName(
  period: { date_from: string; date_to: string },
  supplier: { id: number | null; name: string | null },
  format: ExportFormat
): string {
  let name = `purchases-vs-payments_${period.date_from}_${period.date_to}`;
  if (supplier.name) {
    const slug = supplier.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);
    name += `_${slug || `supplier-${supplier.id}`}`;
  }
  return `${name}.${format}`;
}
