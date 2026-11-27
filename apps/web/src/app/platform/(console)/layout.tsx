import { Suspense } from "react";

import PlatformShell from "@/components/platform/PlatformShell";

/** The platform console. The shell reads the URL, so it renders inside Suspense. */
export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50" />}>
      <PlatformShell>{children}</PlatformShell>
    </Suspense>
  );
}
