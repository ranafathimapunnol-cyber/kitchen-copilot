"use client";

import { createContext, useContext } from "react";

import type { User } from "@/types";

/** The signed-in user, provided by the dashboard shell (no extra request). */
export const CurrentUserContext = createContext<User | null>(null);

export function useCurrentUser(): User | null {
  return useContext(CurrentUserContext);
}
