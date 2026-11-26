"use client";

import { useState } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Field, TextInput } from "@/components/ui/Field";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  hint?: ReactNode;
  error?: string;
};

/** A labelled password field with a show/hide control. */
export default function PasswordInput({
  label,
  hint,
  error,
  required,
  ...props
}: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {({ id, describedBy }) => (
        <div className="relative">
          <TextInput
            {...props}
            id={id}
            type={visible ? "text" : "password"}
            required={required}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            className="pr-11"
          />
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            aria-pressed={visible}
            className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-md p-2 text-slate-500 transition-colors hover:text-slate-700"
          >
            {visible ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      )}
    </Field>
  );
}
