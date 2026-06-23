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
  login: (email: string, password: string) => Promise<boolean>;
  signup: (email: string, password: string, fullName: string, companyName: string) => Promise<boolean>;
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

  const login = async (email: string, password: string): Promise<boolean> => {
    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData,
      });

      if (!res.ok) return false;

      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      setUser(data.user);
      return true;
    } catch (error) {
      console.error("Login failed:", error);
      return false;
    }
  };

  const signup = async (email: string, password: string, fullName: string, companyName: string): Promise<boolean> => {
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

      return res.ok;
    } catch (error) {
      console.error("Signup failed:", error);
      return false;
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