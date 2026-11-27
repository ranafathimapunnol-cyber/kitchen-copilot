"use client";

import { useState } from "react";
import { LogOut, Palette, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api/client";
import { LOGOUT_ALL_ENDPOINT } from "@/lib/api/endpoints";
import { formatRole } from "@/lib/navigation";
import { errorMessage } from "@/lib/payments";
import { useAuth } from "@/hooks/useAuth";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import PageHeader from "@/components/ui/PageHeader";
import ThemePicker from "@/components/ui/ThemePicker";
import { useToast } from "@/components/ui/Toast";

/** Stage 10: the signed-in person's own account and sessions. */
export default function AccountPage() {
  const toast = useToast();
  const { user, logout } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function signOutEverywhere() {
    setBusy(true);
    try {
      await api.post(LOGOUT_ALL_ENDPOINT);
      toast.success("Signed out of every device.");
      await logout();
    } catch (err) {
      toast.error(errorMessage(err, "Could not sign out everywhere."));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={ShieldCheck} eyebrow="Administration" title="Account & Appearance"
        description="Your account, where you are signed in, and how Kitchen Copilot looks on this device." />
      <Card className="max-w-2xl">
        <CardHeader title={user?.full_name ?? "Your account"} subtitle={user ? `${user.email} · ${formatRole(user.role)}` : undefined} />
        <div className="space-y-4 border-t border-slate-100 px-5 py-4 text-sm text-slate-600">
          <p>Lost a phone or used a shared computer? Signing out everywhere ends every session of your account, including this one. You can then sign in again here.</p>
          <p>To change your password, sign out and use <span className="font-medium">Forgot password</span> on the sign-in page.</p>
          <Button variant="danger" icon={<LogOut size={16} />} onClick={() => setConfirming(true)}>Sign out everywhere</Button>
        </div>
      </Card>
      <Card>
        <CardHeader title="Appearance" subtitle="Colour theme for this browser. Your data and permissions are not affected." icon={Palette} iconTone="brand" />
        <div className="p-5 sm:p-6"><ThemePicker /></div>
      </Card>
      <ConfirmDialog open={confirming} tone="warning" title="Sign out of every device?"
        description="Every session of your account ends now, including this one." confirmLabel="Sign out everywhere"
        busy={busy} onCancel={() => setConfirming(false)} onConfirm={signOutEverywhere} />
    </div>
  );
}
