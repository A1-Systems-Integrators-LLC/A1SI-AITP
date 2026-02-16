const BASE_URL = "/api";

function getCsrfToken(): string {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));
  return match ? match.split("=")[1] : "";
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = options?.method ?? "GET";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Add CSRF token for state-changing requests
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    headers["X-CSRFToken"] = getCsrfToken();
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers,
    ...options,
    // Ensure our headers aren't overwritten by spread
  });

  if (response.status === 401) {
    // Redirect to login on auth failure (unless already on login page)
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (response.status === 403) {
    // Possibly a CSRF error — retry once with fresh token
    const body = await response.text();
    if (body.includes("CSRF")) {
      throw new Error("CSRF validation failed. Please refresh and try again.");
    }
    throw new Error(`Forbidden: ${response.statusText}`);
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
