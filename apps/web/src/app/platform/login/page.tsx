"use client";

import { useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";

import { api } from "@/lib/api/client";
import { PLATFORM_API } from "@/lib/platform";
import PasswordInput from "@/components/auth/PasswordInput";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";

/**
 * Platform sign-in (SUPER_ADMIN). Separate from the campus sign-in: its own
 * endpoint, session cookie and audit. There is no registration here;
 * platform accounts are created by the operator.
 */
export default function PlatformLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.post(`${PLATFORM_API}/auth/login`, { email, password });
      router.replace("/platform");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-slate-50 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section aria-hidden className="relative m-3 hidden flex-col justify-between overflow-hidden rounded-[1.5rem] bg-[#171a18] p-12 text-[#f0f0eb] lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#d9f18d] text-[#171a18]"><ShieldCheck size={20} /></span>
          <span className="leading-tight">
            <span className="block text-lg font-semibold tracking-tight">Kitchen Copilot</span>
            <span className="block text-[10px] font-semibold tracking-[0.18em] text-[#f0f0eb]/60 uppercase">Platform administration</span>
          </span>
        </div>
        <div className="max-w-md">
          <p className="text-[2.6rem] leading-[1.05] font-semibold tracking-tight">One organisation.<br />Every campus, kept apart.</p>
          <p className="mt-4 text-[#f0f0eb]/70">Register and manage campuses, see organisation-wide figures and keep the platform healthy. Campus operations stay with each campus.</p>
        </div>
        <p className="text-xs text-[#f0f0eb]/50">Every platform sign-in and action is recorded in the platform audit log.</p>
      </section>

      <section className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <p className="text-[11px] font-semibold tracking-[0.16em] text-slate-500 uppercase">Platform</p>
          <h1 className="mt-1 text-[1.9rem] leading-tight font-semibold tracking-tight text-slate-900">Platform sign-in</h1>
          <p className="mt-2 text-sm text-slate-600">For organisation-level administrators only. Campus staff sign in on the <Link href="/login" className="font-medium text-slate-900 underline">campus sign-in</Link>.</p>
          {error && <Alert tone="error" className="mt-6">{error}</Alert>}
          <form onSubmit={submit} className="mt-6 space-y-5" data-platform-login>
            <Input label="Email address" type="email" autoComplete="username" required autoFocus
              value={email} onChange={(event) => setEmail(event.target.value)} />
            <PasswordInput label="Password" autoComplete="current-password" required
              value={password} onChange={(event) => setPassword(event.target.value)} />
            <Button type="submit" block loading={loading}>Sign in to the platform</Button>
          </form>
          <p className="mt-6 text-xs leading-relaxed text-slate-500">Sessions end after a period set by the operator; sign in again when asked. There is no self-registration.</p>
        </div>
      </section>
    </main>
  );
}
