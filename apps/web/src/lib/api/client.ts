
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const CSRF_ENDPOINT = "/api/auth/csrf";
const REFRESH_ENDPOINT = "/api/auth/refresh";

type ApiOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

let csrfToken: string | null = null;
let redirectingToLogin = false;
let refreshPromise: Promise<boolean> | null = null;

export function clearCsrfToken(): void {
  csrfToken = null;
}

async function getCsrfToken(): Promise<string> {
  if (csrfToken) {
    return csrfToken;
  }

  const response = await fetch(`${API_BASE_URL}${CSRF_ENDPOINT}`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Unable to initialize CSRF protection.");
  }

  const data = (await response.json()) as {
    csrf_token: string;
  };

  csrfToken = data.csrf_token;
  return csrfToken;
}

async function sendRequest(
  endpoint: string,
  options: ApiOptions = {},
): Promise<Response> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);

  headers.set("Accept", "application/json");

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const token = await getCsrfToken();
    headers.set("X-CSRF-Token", token);
  }

  return fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    method,
    headers,
    credentials: "include",
    body:
      options.body === undefined
        ? undefined
        : JSON.stringify(options.body),
    cache: "no-store",
  });
}

async function getErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;

  try {
    const data: unknown = await response.json();

    if (!data || typeof data !== "object") {
      return typeof data === "string" ? data : fallback;
    }

    const body = data as {
      detail?: unknown;
      message?: unknown;
    };

    const detail = body.detail;

    if (typeof detail === "string") return detail;
    if (typeof body.message === "string") return body.message;

    if (Array.isArray(detail)) {
      const messages = detail.map((item) => {
        if (!item || typeof item !== "object") return "";

        const error = item as {
          loc?: unknown[];
          msg?: string;
        };

        const field = error.loc
          ?.filter((part) => part !== "body")
          .map((part) => String(part).replaceAll("_", " "))
          .join(" → ");

        const label = field
          ? field.replace(/\b\w/g, (letter) => letter.toUpperCase())
          : "Input";

        return error.msg ? `${label}: ${error.msg}` : "";
      }).filter(Boolean);

      if (messages.length) return messages.join(" ");
    }

    return fallback;
  } catch {
    return fallback;
  }
}

/**
 * Prevent multiple simultaneous requests from refreshing
 * the session independently.
 */
async function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const response = await sendRequest(REFRESH_ENDPOINT, {
          method: "POST",
        });

        return response.ok;
      } catch {
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
  }

  return refreshPromise;
}

/**
 * Redirect to login only when the user is not already there.
 * This prevents a full-page login refresh loop.
 */
function redirectToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }

  if (window.location.pathname === "/login") {
    return;
  }

  if (redirectingToLogin) {
    return;
  }

  redirectingToLogin = true;
  window.location.replace("/login");
}

export async function apiRequest<T>(
  endpoint: string,
  options: ApiOptions = {},
): Promise<T> {
  let response = await sendRequest(endpoint, options);

  const excludedRefreshRoutes = [
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/csrf",
  ];

  const shouldRefresh =
    response.status === 401 &&
    !excludedRefreshRoutes.includes(endpoint);

  if (shouldRefresh) {
    const refreshed = await refreshSession();

    if (refreshed) {
      // Retry the original request after successful refresh.
      response = await sendRequest(endpoint, options);
    }

    if (!refreshed || response.status === 401) {
      clearCsrfToken();
      redirectToLogin();
    }
  }

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(endpoint: string) =>
    apiRequest<T>(endpoint),

  post: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, {
      method: "POST",
      body,
    }),

  put: <T>(endpoint: string, body: unknown) =>
    apiRequest<T>(endpoint, {
      method: "PUT",
      body,
    }),

  patch: <T>(endpoint: string, body: unknown) =>
    apiRequest<T>(endpoint, {
      method: "PATCH",
      body,
    }),

  delete: <T>(endpoint: string) =>
    apiRequest<T>(endpoint, {
      method: "DELETE",
    }),
};
