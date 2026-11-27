"use client";

import { useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";

import AuthShell from "@/components/auth/AuthShell";
import PasswordInput from "@/components/auth/PasswordInput";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Sign in to Kitchen Copilot"
      description="Use the account your campus admin created for you."
      footer={<>Trouble signing in? Ask your campus admin to check your account. Platform administrator? Use the <Link href="/platform/login" className="font-medium underline">platform sign-in</Link>.</>}
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

        <div className="space-y-2">
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            placeholder="Enter your password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <div className="flex justify-end">
            <Link
              href="/forgot-password"
              className="text-sm font-medium text-brand-600 hover:text-brand-700 hover:underline"
            >
              Forgot password?
            </Link>
          </div>
        </div>

        <Button
          type="submit"
          block
          size="lg"
          loading={loading}
          icon={<LockKeyhole size={16} aria-hidden />}
        >
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  );
}
