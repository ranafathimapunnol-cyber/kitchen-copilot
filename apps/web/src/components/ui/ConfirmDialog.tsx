"use client";

import type { ReactNode } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";

import Button from "./Button";
import Modal from "./Modal";
import { cn } from "./cn";

type Props = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  /** danger = irreversible; warning = reversible but consequential. */
  tone?: "danger" | "warning";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Replaces window.confirm for destructive actions. Focus lands on Cancel,
 * so pressing Enter by reflex never confirms.
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  tone = "danger",
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const Icon = tone === "danger" ? Trash2 : AlertTriangle;

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      dismissible={!busy}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onCancel}
            disabled={busy}
            data-autofocus
          >
            Cancel
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "warning"}
            onClick={onConfirm}
            loading={busy}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex gap-4">
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
            tone === "danger"
              ? "bg-red-50 text-red-600"
              : "bg-amber-50 text-amber-600"
          )}
        >
          <Icon size={18} aria-hidden />
        </div>
        <div className="pt-1.5 text-sm leading-6 text-slate-600">
          {description}
        </div>
      </div>
    </Modal>
  );
}
