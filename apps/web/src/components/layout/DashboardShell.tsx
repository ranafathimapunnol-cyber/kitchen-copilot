
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Menu, X, ChefHat } from "lucide-react";
import Sidebar from "./Sidebar";
import { useAuth } from "@/hooks/useAuth";

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-700 border-t-transparent" />
          Loading workspace...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-sm md:hidden"
        />
      )}

      <Sidebar
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onLogout={logout}
      />

      <div className="min-h-screen md:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen((current) => !current)}
              aria-label="Toggle navigation"
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            >
              {mobileOpen ? <X size={21} /> : <Menu size={21} />}
            </button>

            <div className="flex items-center gap-2 md:hidden">
              <ChefHat size={21} className="text-blue-700" />
              <span className="font-bold text-slate-900">
                Kitchen Copilot
              </span>
            </div>

            <p className="hidden text-sm font-medium text-slate-500 md:block">
              Kitchen Management Workspace
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
              {(user.full_name || user.email).charAt(0).toUpperCase()}
            </div>

            <div className="hidden text-right sm:block">
              <p className="max-w-48 truncate text-sm font-semibold text-slate-800">
                {user.full_name || user.email}
              </p>
              <p className="text-xs capitalize text-slate-500">
                {user.role.replaceAll("_", " ").toLowerCase()}
              </p>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
