"use client";

import { useState } from "react";
import { Tag } from "lucide-react";

import { api } from "@/lib/api/client";
import { itemKindEndpoint } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/payments";
import { ITEM_KINDS, KIND_LABELS, canClassifyItems, type ItemKind } from "@/lib/planning";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ResourcePage from "@/components/shared/ResourcePage";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, SelectInput } from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import Modal from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import type { ResourceConfig } from "@/types";

type Target = { id: number; name: string; kind: ItemKind | null; refresh: () => Promise<void> };

/**
 * The items screen with item classification (Stage 6, decision 6-8): only
 * ADMIN and KITCHEN_MANAGER see the Classify action; the API refuses
 * everyone else, and the item form never sends the kind, so no
 * inventory.* grant can classify an item.
 */
export default function ItemsResourcePage({ config }: { config: ResourceConfig }) {
  const { role } = useAuthorization();
  const [target, setTarget] = useState<Target | null>(null);

  const rowAction = canClassifyItems(role)
    ? (record: Record<string, unknown>, refresh: () => Promise<void>) =>
        record.is_active === false ? null : (
          <IconButton
            size="sm"
            tone="brand"
            icon={<Tag size={15} />}
            label={`Classify ${String(record.name)}`}
            onClick={() => setTarget({ id: Number(record.id), name: String(record.name),
              kind: (record.item_kind as ItemKind | null) ?? null, refresh })}
          />
        )
    : undefined;

  return (
    <>
      <ResourcePage config={config} rowAction={rowAction} />
      {target && <KindModal key={target.id} target={target} onClose={() => setTarget(null)} />}
    </>
  );
}

function KindModal({ target, onClose }: { target: Target; onClose: () => void }) {
  const toast = useToast();
  const [kind, setKind] = useState<string>(target.kind ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (!kind) {
      setError("Choose raw, prepared or outsourced.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.put(itemKindEndpoint(target.id), { item_kind: kind });
      toast.success(`${target.name} classified as ${KIND_LABELS[kind as ItemKind].toLowerCase()}.`);
      await target.refresh();
      onClose();
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to classify the item."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!busy}
      title={`Classify ${target.name}`}
      description="Raw ingredient, prepared food or outsourced food. Portion standards are approved only for raw or prepared items; outsourced items are planned in a later stage. The change is recorded in the audit history."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} loading={busy} disabled={kind === (target.kind ?? "")}>Save</Button>
        </>
      }
    >
      {error && <Alert tone="error" className="mb-4">{error}</Alert>}
      <Field label="Item kind" required hint={target.kind ? "The kind can be changed but not cleared." : undefined}>
        {({ id, describedBy }) => (
          <SelectInput id={id} aria-describedby={describedBy} value={kind} data-autofocus
            onChange={(event) => setKind(event.target.value)}>
            {!target.kind && <option value="">Choose…</option>}
            {ITEM_KINDS.map((value) => (
              <option key={value} value={value}>{KIND_LABELS[value]}</option>
            ))}
          </SelectInput>
        )}
      </Field>
    </Modal>
  );
}
