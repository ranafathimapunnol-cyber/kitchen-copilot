"use client";

import { useState } from "react";
import { LogOut } from "lucide-react";

import { formatDateTime } from "@/lib/payments";
import Button from "@/components/ui/Button";
import ThemePicker from "@/components/ui/ThemePicker";
import { PlatformHeader, Section } from "@/components/platform/parts";
import { platformSignOut, usePlatformUser } from "@/components/platform/PlatformShell";

/** The platform account, its session and appearance. */
export default function PlatformSettingsPage() {
  const user = usePlatformUser();
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Settings" description="Your platform account, session and appearance." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Account">
          <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-4 gap-y-2.5 px-5 py-4 text-sm">
            <dt className="text-slate-500">Name</dt><dd className="font-medium text-slate-900">{user.full_name}</dd>
            <dt className="text-slate-500">Email</dt><dd>{user.email}</dd>
            <dt className="text-slate-500">Role</dt><dd>Platform administrator{user.organization_id ? " (one organisation)" : " (all organisations)"}</dd>
            <dt className="text-slate-500">Last sign-in</dt><dd>{formatDateTime(user.last_login_at)}</dd>
          </dl>
        </Section>
        <Section title="Session">
          <div className="space-y-3 px-5 py-4 text-sm text-slate-600">
            <p>Platform sessions last {user.session_minutes} minutes and are not extended; sign in again when asked. Signing out ends every platform session of this account, on every device.</p>
            <p>Self-service password reset is not enabled for platform accounts yet; the operator changes platform passwords.</p>
            <Button variant="danger" icon={<LogOut size={15} />} loading={busy} onClick={() => { setBusy(true); void platformSignOut(); }}>Sign out everywhere</Button>
          </div>
        </Section>
        <Section title="Appearance" className="lg:col-span-2">
          <div className="px-5 py-4"><ThemePicker /></div>
        </Section>
      </div>
    </div>
  );
}
