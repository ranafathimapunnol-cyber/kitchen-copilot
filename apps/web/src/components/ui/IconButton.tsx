import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

type Tone = "neutral" | "brand" | "warning" | "danger";

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  /** Required: an icon-only button has no other accessible name. */
  label: string;
  icon: ReactNode;
  tone?: Tone;
  size?: "sm" | "md";
};

const tones: Record<Tone, string> = {
  neutral: "text-slate-500 hover:bg-slate-100 hover:text-slate-900",
  brand: "text-slate-500 hover:bg-brand-50 hover:text-brand-700",
  warning: "text-slate-500 hover:bg-amber-50 hover:text-amber-700",
  danger: "text-slate-500 hover:bg-red-50 hover:text-red-700",
};

export default function IconButton({
  label,
  icon,
  tone = "neutral",
  size = "md",
  className,
  type = "button",
  ...props
}: Props) {
  return (
    <button
      {...props}
      type={type}
      aria-label={label}
      title={props.title ?? label}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg transition-colors disabled:pointer-events-none disabled:opacity-35",
        size === "sm" ? "h-8 w-8" : "h-9 w-9",
        tones[tone],
        className
      )}
    >
      {icon}
    </button>
  );
}
