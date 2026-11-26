import type { InputHTMLAttributes, ReactNode } from "react";

import { Field, TextInput } from "./Field";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: ReactNode;
  error?: string;
};

/** A labelled text input. For other controls use Field directly. */
export default function Input({
  label,
  hint,
  error,
  required,
  ...props
}: Props) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {({ id, describedBy }) => (
        <TextInput
          {...props}
          id={id}
          required={required}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
        />
      )}
    </Field>
  );
}
