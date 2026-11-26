"use client";

import { useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { MailCheck, Send } from "lucide-react";

import AuthShell from "@/components/auth/AuthShell";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";

// Shown whatever happens on the server, so the page never reveals whether
// an account exists. Matches the API's own response.
const GENERIC_MESSAGE =
  "If an eligible account exists for this email address, password reset instructions will be sent.";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSending(true);
    setError("");

    try {
      await api.post(ENDPOINTS.passwordForgot, { email });
      setSent(true);
    } catch (err) {
      // Only rate limits and malformed input land here; neither says
      // anything about whether the account exists.
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  };

  const backToSignIn = (
    <Link
      href="/login"
      className="font-semibold text-brand-600 hover:text-brand-700 hover:underline"
    >
      Back to sign in
    </Link>
  );

  if (sent) {
    return (
      <AuthShell title="Check your email" footer={backToSignIn}>
        <div className="flex flex-col items-center text-center" role="status">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <MailCheck size={24} aria-hidden />
          </div>
          <p className="mt-4 text-sm text-slate-600">{GENERIC_MESSAGE}</p>
          <p className="mt-3 text-xs text-slate-500">
            The link expires soon and works once. Nothing arrived after a few
            minutes? Check your spam folder, then try again.
          </p>
          <Button
            variant="secondary"
            block
            className="mt-6"
            onClick={() => {
              setSent(false);
              setEmail("");
            }}
          >
            Use a different email
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot your password?"
      description="Enter the email address you sign in with and we'll send you a secure link to reset it."
      footer={backToSignIn}
    >
      {error && (
        <Alert tone="error" className="mb-5">
          {error}
        </Alert>
      )}

      <form onSubmit={submit} className="space-y-5">
        <Input
          label="Email address"
          type="email"
          autoComplete="username"
          placeholder="name@example.com"
          required
          autoFocus
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <Button
          type="submit"
          block
          size="lg"
          loading={sending}
          icon={<Send size={16} aria-hidden />}
        >
          Send reset link
        </Button>
      </form>

      <p className="mt-5 text-xs text-slate-500">
        Reset by email is for administrator accounts. Kitchen managers and
        staff: ask your campus administrator to reset your password.
      </p>
    </AuthShell>
  );
}
