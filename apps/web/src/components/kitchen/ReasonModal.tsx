"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, TextArea } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";

/**
 * Asks for a reason (at least 3 characters) before cancelling a draft or
 * reversing a confirmed document. Mount it with a key per document so a
 * reason typed for one never carries over to another.
 */
export default function ReasonModal({
  open,
  title,
  description,
  confirmLabel,
  tone = "warning",
  placeholder,
  onSubmit,
  onClose,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  tone?: "warning" | "danger";
  placeholder?: string;
  onSubmit: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (reason.trim().length < 3) {
      setError("Give a reason (at least 3 characters).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit(reason.trim());
    } catch (err: unknown) {
      setError(err instanceof Error && err.message ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => (busy ? undefined : onClose())}
      dismissible={!busy}
      size="sm"
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Keep it</Button>
          <Button variant={tone} loading={busy} onClick={submit}>{confirmLabel}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Reason" required>
          {({ id }) => (
            <TextArea id={id} rows={3} maxLength={500} data-autofocus value={reason} placeholder={placeholder}
              onChange={(event) => setReason(event.target.value)} />
          )}
        </Field>
      </div>
    </Modal>
  );
}
