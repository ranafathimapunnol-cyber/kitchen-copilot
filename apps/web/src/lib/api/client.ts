
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const CSRF_ENDPOINT = "/api/auth/csrf";
const REFRESH_ENDPOINT = "/api/auth/refresh";

type ApiOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

let csrfToken: string | null = null;
let redirectingToLogin = false;

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
  let message = `Request failed (${response.status})`;

  try {
    const data = await response.json();

    message =
      data.detail ||
      data.message ||
      (typeof data === "string" ? data : message);
  } catch {
    // Keep the default error message.
  }

  return typeof message === "string"
    ? message
    : JSON.stringify(message);
}

function redirectToLogin(): void {
  if (typeof window === "undefined" || redirectingToLogin) {
    return;
  }

  redirectingToLogin = true;
  window.location.assign("/login");
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

  if (
    response.status === 401 &&
    !excludedRefreshRoutes.includes(endpoint)
  ) {
    try {
      const refreshResponse = await sendRequest(REFRESH_ENDPOINT, {
        method: "POST",
      });

      if (refreshResponse.ok) {
        response = await sendRequest(endpoint, options);
      } else {
        clearCsrfToken();
        redirectToLogin();
      }
    } catch {
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
  get: <T>(endpoint: string) => apiRequest<T>(endpoint),

  post: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, { method: "POST", body }),

  put: <T>(endpoint: string, body: unknown) =>
    apiRequest<T>(endpoint, { method: "PUT", body }),

  patch: <T>(endpoint: string, body: unknown) =>
    apiRequest<T>(endpoint, { method: "PATCH", body }),

  delete: <T>(endpoint: string) =>
    apiRequest<T>(endpoint, { method: "DELETE" }),
};
