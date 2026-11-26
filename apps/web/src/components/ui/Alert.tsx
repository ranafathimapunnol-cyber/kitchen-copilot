import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
} from "lucide-react";

import { cn } from "./cn";

type Tone = "error" | "success" | "warning" | "info";

const tones: Record<Tone, { box: string; icon: typeof Info }> = {
  error: { box: "border-red-200 bg-red-50 text-red-800", icon: XCircle },
  success: {
    box: "border-emerald-200 bg-emerald-50 text-emerald-800",
    icon: CheckCircle2,
  },
  warning: {
    box: "border-amber-200 bg-amber-50 text-amber-900",
    icon: AlertTriangle,
  },
  info: { box: "border-brand-200 bg-brand-50 text-brand-800", icon: Info },
};

export default function Alert({
  tone = "info",
  title,
  children,
  onDismiss,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}) {
  const { box, icon: Icon } = tones[tone];

  return (
    <div
      // Errors interrupt; everything else is announced politely.
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-3 text-sm",
        box,
        className
      )}
    >
      <Icon size={18} className="mt-px shrink-0" aria-hidden />

      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && (
          <div className={cn(title && "mt-0.5", "wrap-break-word")}>
            {children}
          </div>
        )}
      </div>

      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-m-1 rounded-md p-1 opacity-70 transition-opacity hover:opacity-100"
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
