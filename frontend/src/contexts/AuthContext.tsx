import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

interface AuthUser {
  id: number;
  email: string;
  username: string;
}

interface AuthContextType {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Restore the auth token from localStorage at initialisation time.
 * The token is then VALIDATED against the backend (/api/auth/me) — a stale
 * or invalid token previously left the app looking "logged in" while every
 * API call silently failed with 401.
 */
function getInitialToken(): string | null {
  const stored = localStorage.getItem('auth_token');
  if (stored) {
    api.setToken(stored);
  }
  return stored;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(getInitialToken);
  const [user, setUser] = useState<AuthUser | null>(null);
  // Loading while we validate a restored token with the server.
  const [isLoading, setIsLoading] = useState<boolean>(() => !!token);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('auth_token');
    api.setToken(null);
  }, []);

  // Validate restored token on mount; drop it if the server rejects it.
  useEffect(() => {
    let cancelled = false;
    if (!token) return;
    (async () => {
      try {
        const me = await api.getMe();
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) logout();
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Run only for the initially-restored token; login() sets user itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Any API call that returns 401 (expired/invalid token) logs us out.
  useEffect(() => {
    const onUnauthorized = () => logout();
    window.addEventListener('auth:unauthorized', onUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', onUnauthorized);
  }, [logout]);

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password);
    const newToken = response.access_token;
    localStorage.setItem('auth_token', newToken);
    api.setToken(newToken);
    setToken(newToken);
    try {
      setUser(await api.getMe());
    } catch {
      setUser(null);
    }
  };

  const register = async (email: string, password: string) => {
    await api.register(email, password);
    await login(email, password);
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token,
        login,
        register,
        logout,
        isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
