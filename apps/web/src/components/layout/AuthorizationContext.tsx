"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";

type AuthorizationResponse = {
  user_id: number;
  role: string;
  permissions: string[];
};

type AuthorizationContextType = {
  role: string;
  permissions: string[];
  loading: boolean;
  error: string;
};

const AuthorizationContext =
  createContext<AuthorizationContextType>({
    role: "",
    permissions: [],
    loading: true,
    error: "",
  });

export function AuthorizationProvider({
  userId,
  children,
}: {
  userId: string | number;
  children: React.ReactNode;
}) {
  const [role, setRole] = useState("");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [error, setError] = useState("");

  // The user whose permissions have finished loading. Loading is derived
  // from it, so it is true on the first render and whenever userId changes,
  // without setting state synchronously inside the effect.
  const [loadedUserId, setLoadedUserId] = useState<string | number | null>(
    null
  );
  const loading = loadedUserId !== userId;

  useEffect(() => {
    let active = true;

    api
      .get<AuthorizationResponse>(ENDPOINTS.authorizationMe)
      .then((response) => {
        if (active) {
          setRole(response.role ?? "");
          setPermissions(response.permissions ?? []);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setRole("");
          setPermissions([]);
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load permissions."
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoadedUserId(userId);
        }
      });

    return () => {
      active = false;
    };
  }, [userId]);

  return (
    <AuthorizationContext.Provider
      value={{ role, permissions, loading, error }}
    >
      {children}
    </AuthorizationContext.Provider>
  );
}

export function useAuthorization() {
  return useContext(AuthorizationContext);
}
