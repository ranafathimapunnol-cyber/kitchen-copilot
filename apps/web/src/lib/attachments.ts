/**
 * Bill attachment rules (approved 18 November 2026), checked in the browser
 * before upload so mistakes show at once. The API checks again from the
 * file's actual content and is authoritative. No imports, so `node --test`
 * can run its tests directly.
 */

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export const MAX_ATTACHMENTS_PER_BILL = 10;

/** Extension → MIME type of the accepted formats. */
export const ATTACHMENT_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

/** For the file picker's `accept` attribute. */
export const ATTACHMENT_ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp";

export type PickedFile = { name: string; size: number; type: string };

export type FileCheck = {
  accepted: PickedFile[];
  rejected: { name: string; reason: string }[];
};

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

/** Splits picked files into those worth uploading and those that would be
 * refused, given how many the bill already has. */
export function checkFiles(files: PickedFile[], alreadyAttached: number): FileCheck {
  const result: FileCheck = { accepted: [], rejected: [] };
  let room = Math.max(MAX_ATTACHMENTS_PER_BILL - alreadyAttached, 0);

  for (const file of files) {
    const knownType =
      Object.values(ATTACHMENT_TYPES).includes(file.type) ||
      extension(file.name) in ATTACHMENT_TYPES;

    if (!knownType) {
      result.rejected.push({ name: file.name, reason: "Only PDF, JPEG, PNG or WEBP files." });
    } else if (file.size === 0) {
      result.rejected.push({ name: file.name, reason: "The file is empty." });
    } else if (file.size > MAX_ATTACHMENT_BYTES) {
      result.rejected.push({ name: file.name, reason: "Larger than 10 MB." });
    } else if (room === 0) {
      result.rejected.push({
        name: file.name,
        reason: `A bill can have at most ${MAX_ATTACHMENTS_PER_BILL} attachments.`,
      });
    } else {
      result.accepted.push(file);
      room -= 1;
    }
  }
  return result;
}

/** 1536 → "1.5 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : Math.round(value * 10) / 10} ${units[unit]}`;
}
