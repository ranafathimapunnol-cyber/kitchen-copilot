"use client";

import { Field, TextArea, TextInput } from "@/components/ui/Field";

export type CampusForm = { name: string; code: string; address: string; contact_name: string; contact_email: string; contact_phone: string };
export const EMPTY_FORM: CampusForm = { name: "", code: "", address: "", contact_name: "", contact_email: "", contact_phone: "" };

export function CampusFields({ form, setForm, withCode }: { form: CampusForm; setForm: (f: CampusForm) => void; withCode: boolean }) {
  const set = (key: keyof CampusForm) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Campus name" required className="sm:col-span-2">{({ id }) => <TextInput id={id} value={form.name} onChange={set("name")} maxLength={150} data-autofocus />}</Field>
      {withCode && (
        <Field label="Campus code" required hint="2–30 letters, digits, - or _. Fixed once created (it appears on documents).">
          {({ id, describedBy }) => <TextInput id={id} aria-describedby={describedBy} value={form.code} onChange={set("code")} maxLength={30} />}
        </Field>
      )}
      <Field label="Contact person">{({ id }) => <TextInput id={id} value={form.contact_name} onChange={set("contact_name")} maxLength={150} />}</Field>
      <Field label="Contact email">{({ id }) => <TextInput id={id} type="email" value={form.contact_email} onChange={set("contact_email")} />}</Field>
      <Field label="Contact phone">{({ id }) => <TextInput id={id} type="tel" value={form.contact_phone} onChange={set("contact_phone")} maxLength={40} />}</Field>
      <Field label="Address" className="sm:col-span-2">{({ id }) => <TextArea id={id} rows={2} value={form.address} onChange={set("address")} maxLength={500} />}</Field>
    </div>
  );
}

export const formBody = (f: CampusForm) => ({
  name: f.name, address: f.address || null, contact_name: f.contact_name || null,
  contact_email: f.contact_email || null, contact_phone: f.contact_phone || null,
});

