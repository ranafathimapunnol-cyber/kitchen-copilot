"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, CheckCircle2, Circle, KeyRound, Link2Off } from "lucide-react";

import AuthShell from "./AuthShell";
import PasswordInput from "./PasswordInput";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Spinner } from "@/components/ui/States";
import { cn } from "@/components/ui/cn";
import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";

type Purpose = "setup" | "reset";

type ChangeResult = {
  message: string;
  confirmation_email_sent: boolean;
};

const MIN_LENGTH = 8;
const REDIRECT_MS = 6000;

const COPY: Record<
  Purpose,
  { title: string; description: string; submit: string; done: string }
> = {
  setup: {
    title: "Set your password",
    description:
      "Choose the password you'll use to sign in to Kitchen Copilot.",
    submit: "Set password",
    done: "Password set",
  },
  reset: {
    title: "Choose a new password",
    description:
      "Your new password replaces the old one and signs out every device.",
    submit: "Reset password",
    done: "Password reset",
  },
};

// The token arrives in the URL fragment (#token=...), which browsers never
// send to a server. Reading it through useSyncExternalStore gives null on
// the server render and the real value once hydrated.
function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function readToken(hash: string | null): string | null {
  if (hash === null) return null;
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return token && token.length >= 16 ? token : "";
}

function Rule({ met, children }: { met: boolean; children: string }) {
  const Icon = met ? Check : Circle;
  return (
    <li
      className={cn(
        "flex items-center gap-2 text-xs",
        met ? "text-emerald-700" : "text-slate-500"
      )}
    >
      <Icon size={13} aria-hidden />
      {children}
      <span className="sr-only">{met ? "(met)" : "(not yet met)"}</span>
    </li>
  );
}

export default function PasswordLinkForm({ purpose }: { purpose: Purpose }) {
  const router = useRouter();
  const copy = COPY[purpose];

  const hash = useSyncExternalStore(
    subscribeToHash,
    () => window.location.hash,
    () => null
  );
  const token = readToken(hash);

  const [check, setCheck] = useState<{
    token: string;
    valid: boolean;
    message: string;
  } | null>(null);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ChangeResult | null>(null);

  // Ask the API whether the link still works, so a dead link is reported
  // before anyone types a password. State is set only in callbacks.
  useEffect(() => {
    if (!token) return;
    let active = true;

    api
      .post(ENDPOINTS.passwordVerify, { token, purpose })
      .then(() => {
        if (active) setCheck({ token, valid: true, message: "" });
      })
      .catch((err: unknown) => {
        if (active) {
          setCheck({
            token,
            valid: false,
            message: err instanceof Error ? err.message : "",
          });
        }
      });

    return () => {
      active = false;
    };
  }, [token, purpose]);

  // After success, continue to sign-in on our own.
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(() => router.replace("/login"), REDIRECT_MS);
    return () => window.clearTimeout(timer);
  }, [result, router]);

  const linkState: "checking" | "valid" | "invalid" =
    token === null
      ? "checking"
      : token === ""
        ? "invalid"
        : check?.token === token
          ? check.valid
            ? "valid"
            : "invalid"
          : "checking";

  const longEnough = password.length >= MIN_LENGTH;
  const matches = password.length > 0 && password === confirm;

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    if (!longEnough) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }

    if (!matches) {
      setError("The two passwords don't match.");
      return;
    }

    setSaving(true);

    try {
      const response = await api.post<ChangeResult>(
        purpose === "setup" ? ENDPOINTS.passwordSetup : ENDPOINTS.passwordReset,
        { token, new_password: password, confirm_password: confirm }
      );

      // The link is spent; take it out of the address bar and history.
      window.history.replaceState(null, "", window.location.pathname);
      setPassword("");
      setConfirm("");
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  };

  // ---- Done ---------------------------------------------------------------
  if (result) {
    return (
      <AuthShell title={copy.done}>
        <div className="flex flex-col items-center text-center" role="status">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={24} aria-hidden />
          </div>
          <p className="mt-4 text-sm text-slate-600">{result.message}</p>

          {!result.confirmation_email_sent && (
            <Alert tone="warning" className="mt-4 text-left">
              Your password was changed, but we couldn&apos;t send the
              confirmation email.
            </Alert>
          )}

          <Button
            block
            size="lg"
            className="mt-6"
            onClick={() => router.replace("/login")}
          >
            Continue to sign in
          </Button>
          <p className="mt-3 text-xs text-slate-500">
            Taking you to sign in automatically…
          </p>
        </div>
      </AuthShell>
    );
  }

  // ---- Link check ---------------------------------------------------------
  if (linkState === "checking") {
    return (
      <AuthShell title={copy.title}>
        <Spinner label="Checking your link…" className="py-10" />
      </AuthShell>
    );
  }

  if (linkState === "invalid") {
    const rateLimited = /too many/i.test(check?.message ?? "");

    return (
      <AuthShell
        title={rateLimited ? "Please wait a moment" : "This link can't be used"}
        footer={
          <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-700 hover:underline">
            Back to sign in
          </Link>
        }
      >
        <div className="flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <Link2Off size={22} aria-hidden />
          </div>
          <p className="mt-4 text-sm text-slate-600">
            {rateLimited
              ? check?.message
              : purpose === "setup"
                ? "Setup links expire and work only once. If yours has expired, request a new one with Forgot password."
                : "Reset links expire after a short time and work only once. Request a new one to continue."}
          </p>
          {!rateLimited && (
            <Button
              block
              size="lg"
              className="mt-6"
              onClick={() => router.push("/forgot-password")}
            >
              Request a new link
            </Button>
          )}
        </div>
      </AuthShell>
    );
  }

  // ---- Form ---------------------------------------------------------------
  return (
    <AuthShell
      title={copy.title}
      description={copy.description}
      footer={
        <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-700 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {error && (
        <Alert tone="error" className="mb-5">
          {error}
        </Alert>
      )}

      <form onSubmit={submit} className="space-y-5" noValidate>
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          required
          autoFocus
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        <PasswordInput
          label="Confirm new password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />

        <ul className="space-y-1.5" aria-label="Password requirements">
          <Rule met={longEnough}>{`At least ${MIN_LENGTH} characters`}</Rule>
          <Rule met={matches}>Both passwords match</Rule>
        </ul>

        <Button
          type="submit"
          block
          size="lg"
          loading={saving}
          icon={<KeyRound size={16} aria-hidden />}
        >
          {copy.submit}
        </Button>
      </form>
    </AuthShell>
  );
}
