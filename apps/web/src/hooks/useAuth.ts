
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, clearCsrfToken } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";
import type { User } from "@/types";

export function useAuth() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const currentUser = await api.get<User>(ENDPOINTS.me);
      setUser(currentUser);
      return currentUser;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    const initializeAuth = async () => {
      try {
        const currentUser = await api.get<User>(ENDPOINTS.me);

        if (active) {
          setUser(currentUser);
        }
      } catch {
        if (active) {
          setUser(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void initializeAuth();

    return () => {
      active = false;
    };
  }, []);

  const login = async (email: string, password: string) => {
    await api.post<User>(ENDPOINTS.login, {
      email,
      password,
    });

    const currentUser = await api.get<User>(ENDPOINTS.me);

    setUser(currentUser);
    return currentUser;
  };

  const logout = async () => {
    try {
      await api.post<{ message: string }>(ENDPOINTS.logout);
    } finally {
      clearCsrfToken();
      setUser(null);
      router.replace("/login");
    }
  };

  return {
    user,
    loading,
    login,
    logout,
    refreshUser,
  };
}
