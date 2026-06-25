"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { API_BASE } from "../../lib/api";

interface User {
  id: number;
  email: string;
  full_name: string;
  company_name: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  signup: (email: string, password: string, fullName: string, companyName: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedToken = localStorage.getItem("token");
    if (savedToken) {
      setToken(savedToken);
      fetchUser(savedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchUser = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const userData = await res.json();
        setUser(userData);
      } else {
        localStorage.removeItem("token");
        setToken(null);
      }
    } catch (error) {
      console.error("Failed to fetch user:", error);
    } finally {
      setIsLoading(false);
    }
  };

  function parseErrorDetail(detail: unknown, fallback: string): string {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: string }).msg)
            : String(item)
        )
        .join(". ");
    }
    return fallback;
  }

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData,
      });

      const text = await res.text();
      let data: { detail?: unknown; access_token?: string; user?: User };
      try {
        data = JSON.parse(text);
      } catch {
        return { success: false, error: text || "Invalid email or password" };
      }

      if (!res.ok) {
        return { success: false, error: parseErrorDetail(data.detail, "Invalid email or password") };
      }

      if (!data.access_token) {
        return { success: false, error: "No token received from server" };
      }

      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      if (data.user) setUser(data.user);
      return { success: true };
    } catch (error) {
      console.error("Login failed:", error);
      return { success: false, error: "Network error. Please try again." };
    }
  };

  const signup = async (email: string, password: string, fullName: string, companyName: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const formData = new URLSearchParams();
      formData.append("email", email);
      formData.append("password", password);
      formData.append("full_name", fullName);
      formData.append("company_name", companyName);

      const res = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData,
      });

      const text = await res.text();
      let data: { detail?: unknown };
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }

      if (!res.ok) {
        return {
          success: false,
          error: parseErrorDetail(
            data.detail,
            res.status === 400
              ? "This email may already be registered."
              : `Failed to create account (${res.status}).`
          ),
        };
      }

      // Auto-login after successful registration
      return await login(email, password);
    } catch (error) {
      console.error("Signup failed:", error);
      return { success: false, error: "Network error. Please try again." };
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, signup, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}