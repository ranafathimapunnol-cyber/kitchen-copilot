"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ChefHat, LockKeyhole } from "lucide-react";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
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
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/60">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-700 text-white">
            <ChefHat size={30} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Kitchen Copilot
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Sign in to manage your kitchen and mess operations.
          </p>
        </div>

        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="space-y-5">
          <Input
            label="Email address"
            type="email"
            autoComplete="username"
            placeholder="name@example.com"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <Button type="submit" block className="w-full py-3" disabled={loading}>
            <LockKeyhole size={16} className="mr-2" />
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </form>

        <p className="mt-7 text-center text-xs text-slate-400">
          Authorized campus users only
        </p>
      </div>
    </main>
  );
}
