import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "./cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "warning";

export type ButtonSize = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Stretches to the container width. */
  block?: boolean;
  /** Shows a spinner and disables the button. */
  loading?: boolean;
  /** Icon shown before the label; replaced by the spinner while loading. */
  icon?: ReactNode;
};

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-600 text-white shadow-[0_1px_2px_rgb(56_45_37/0.12),inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-brand-700 active:bg-brand-800",
  secondary:
    "border border-slate-200 bg-white text-slate-800 shadow-xs hover:border-brand-200 hover:bg-brand-50/60 active:bg-brand-50",
  ghost: "text-slate-600 hover:bg-brand-50 hover:text-slate-900",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700 active:bg-red-800",
  warning:
    "bg-amber-600 text-white shadow-sm hover:bg-amber-700 active:bg-amber-800",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 px-3 text-[13px]",
  md: "h-10 gap-2 px-4 text-sm",
  lg: "h-11 gap-2 px-5 text-sm",
};

export default function Button({
  children,
  variant = "primary",
  size = "md",
  block = false,
  loading = false,
  icon,
  className,
  disabled,
  type = "button",
  ...props
}: Props) {
  return (
    <button
      {...props}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-[10px] font-medium tracking-[0.005em] transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-out active:scale-[0.985] disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        block && "w-full",
        className
      )}
    >
      {loading ? (
        <Loader2 size={16} className="animate-spin" aria-hidden />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
