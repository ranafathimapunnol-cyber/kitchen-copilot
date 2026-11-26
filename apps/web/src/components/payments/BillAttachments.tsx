"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Eye, FileText, ImageIcon, Paperclip } from "lucide-react";

import { api, apiDownload } from "@/lib/api/client";
import {
  billAttachmentFileEndpoint,
  billAttachmentsEndpoint,
} from "@/lib/api/endpoints";
import {
  ATTACHMENT_ACCEPT,
  MAX_ATTACHMENTS_PER_BILL,
  checkFiles,
  formatBytes,
} from "@/lib/attachments";
import { errorMessage, formatDateTime, type BillAttachment } from "@/lib/payments";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

/**
 * The files attached to one supplier bill: scans, photos or PDFs of the
 * original bill. Attachments are permanent; a wrong file is superseded by
 * attaching the right one with a remark.
 */
export default function BillAttachments({
  purchaseId,
  canUpload,
}: {
  purchaseId: number;
  canUpload: boolean;
}) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<BillAttachment[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [remark, setRemark] = useState("");
  const [uploading, setUploading] = useState(false);
  const [problems, setProblems] = useState<{ name: string; reason: string }[]>([]);

  useEffect(() => {
    let active = true;
    api
      .get<{ items: BillAttachment[] }>(billAttachmentsEndpoint(purchaseId))
      .then((response) => {
        if (active) {
          setItems(response.items);
          setLoadError("");
        }
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load attachments."));
      });
    return () => {
      active = false;
    };
  }, [purchaseId, reloadKey]);

  async function attach(fileList: FileList | null) {
    if (!fileList?.length || !items) return;
    const files = Array.from(fileList);
    const { accepted, rejected } = checkFiles(files, items.length);
    const found = [...rejected];
    let added = 0;

    setUploading(true);
    for (const file of accepted as File[]) {
      const form = new FormData();
      form.append("file", file);
      if (remark.trim()) form.append("remarks", remark.trim());
      try {
        await api.upload(billAttachmentsEndpoint(purchaseId), form);
        added += 1;
      } catch (err: unknown) {
        found.push({ name: file.name, reason: errorMessage(err, "Upload failed.") });
      }
    }
    setUploading(false);
    setProblems(found);
    if (input.current) input.current.value = "";

    if (added) {
      toast.success(`${added} file${added === 1 ? "" : "s"} attached.`);
      setRemark("");
      setReloadKey((key) => key + 1);
    }
  }

  async function open(item: BillAttachment, inline: boolean) {
    try {
      const { blob, filename } = await apiDownload(
        billAttachmentFileEndpoint(purchaseId, item.id, inline)
      );
      const url = URL.createObjectURL(blob);
      if (inline) {
        window.open(url, "_blank", "noopener");
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename ?? item.original_filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err: unknown) {
      toast.error(errorMessage(err, "The file could not be opened."));
    }
  }

  const full = (items?.length ?? 0) >= MAX_ATTACHMENTS_PER_BILL;

  return (
    <section aria-labelledby={`attachments-${purchaseId}`} className="space-y-3" data-bill-attachments>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`attachments-${purchaseId}`} className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Paperclip size={15} aria-hidden className="text-slate-400" />
          Attachments
        </h3>
        {items && (
          <span className="text-xs text-slate-500">
            {items.length} of {MAX_ATTACHMENTS_PER_BILL} · PDF, JPEG, PNG or WEBP, up to 10 MB each
          </span>
        )}
      </div>

      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !items ? (
        <Spinner label="Loading attachments" />
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">No files attached to this bill.</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200" data-attachment-list>
          {items.map((item) => {
            const Icon = item.content_type === "application/pdf" ? FileText : ImageIcon;
            return (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <span className="flex min-w-0 items-center gap-3">
                  <Icon size={16} aria-hidden className="shrink-0 text-slate-400" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-900">{item.original_filename}</span>
                    <span className="block text-xs text-slate-500">
                      {formatBytes(item.size_bytes)} · {formatDateTime(item.uploaded_at)}
                      {item.uploaded_by_name && ` · ${item.uploaded_by_name}`}
                      {item.remarks && ` · ${item.remarks}`}
                    </span>
                  </span>
                </span>
                <span className="flex shrink-0 gap-1.5">
                  <Button size="sm" variant="ghost" icon={<Eye size={14} aria-hidden />} onClick={() => void open(item, true)}>
                    View
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Download size={14} aria-hidden />} onClick={() => void open(item, false)}>
                    Download
                  </Button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {problems.length > 0 && (
        <Alert tone="error" title="Not attached">
          <ul className="list-disc pl-4">
            {problems.map((problem, index) => (
              <li key={`${problem.name}-${index}`}>
                {problem.name}: {problem.reason}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      {canUpload && items && !full && (
        <div className="flex flex-col gap-3 rounded-lg border border-dashed border-slate-300 p-3 sm:flex-row sm:items-end">
          <Field label="Remark for these files (optional)" className="flex-1">
            {({ id }) => (
              <TextInput
                id={id}
                maxLength={500}
                value={remark}
                disabled={uploading}
                placeholder="e.g. Original bill, page 1"
                onChange={(event) => setRemark(event.target.value)}
              />
            )}
          </Field>
          <input
            ref={input}
            type="file"
            multiple
            accept={ATTACHMENT_ACCEPT}
            className="sr-only"
            aria-label="Choose files to attach"
            data-attachment-input
            onChange={(event) => void attach(event.target.files)}
          />
          <Button
            variant="secondary"
            icon={<Paperclip size={15} aria-hidden />}
            loading={uploading}
            onClick={() => input.current?.click()}
          >
            Attach files
          </Button>
        </div>
      )}
      {canUpload && full && (
        <p className="text-xs text-slate-500">This bill has the maximum of {MAX_ATTACHMENTS_PER_BILL} attachments.</p>
      )}
      {canUpload && (
        <p className="text-xs text-slate-500">
          Attachments can&apos;t be removed. If a file is wrong, attach the right one with a remark.
        </p>
      )}
    </section>
  );
}
