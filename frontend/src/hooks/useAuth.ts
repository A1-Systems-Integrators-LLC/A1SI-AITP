import { useCallback, useEffect, useState } from "react";

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  username: string | null;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    username: null,
  });

  const checkAuth = useCallback(async () => {
    try {
      const resp = await fetch("/api/auth/status/", {
        credentials: "include",
      });
      if (resp.ok) {
        const data = await resp.json();
        setState({
          isAuthenticated: data.authenticated,
          isLoading: false,
          username: data.username ?? null,
        });
      } else {
        setState({ isAuthenticated: false, isLoading: false, username: null });
      }
    } catch {
      setState({ isAuthenticated: false, isLoading: false, username: null });
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(
    async (username: string, password: string): Promise<string | null> => {
      // Get CSRF token first
      const csrfMatch = document.cookie
        .split("; ")
        .find((row) => row.startsWith("csrftoken="));
      const csrfToken = csrfMatch ? csrfMatch.split("=")[1] : "";

      const resp = await fetch("/api/auth/login/", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await resp.json();
      if (resp.ok) {
        setState({
          isAuthenticated: true,
          isLoading: false,
          username: data.username,
        });
        return null; // no error
      }
      return data.error ?? "Login failed";
    },
    [],
  );

  const logout = useCallback(async () => {
    const csrfMatch = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    const csrfToken = csrfMatch ? csrfMatch.split("=")[1] : "";

    await fetch("/api/auth/logout/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": csrfToken },
    });
    setState({ isAuthenticated: false, isLoading: false, username: null });
  }, []);

  return { ...state, login, logout, checkAuth };
}
