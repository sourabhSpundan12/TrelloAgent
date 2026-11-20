import React, { createContext, useContext, useEffect, useState } from 'react';
import { AuthUser, LoginCredentials, RegisterPayload } from '../types';
import {
  clearStoredTokens,
  fetchCurrentUser,
  getStoredToken,
  loginUser,
  registerUser,
  silentRefreshToken,
} from '../services/api';

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginModalOpen: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  openLoginModal: () => void;
  closeLoginModal: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loginModalOpen, setLoginModalOpen] = useState<boolean>(false);

  const initAuth = async () => {
    const token = getStoredToken();
    const hasRefreshToken = !!localStorage.getItem('refresh_token');

    if (!token && !hasRefreshToken) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const userData = await fetchCurrentUser();
      setUser(userData);
    } catch (err) {
      // If access token expired, attempt silent token refresh before giving up
      if (hasRefreshToken) {
        try {
          const newToken = await silentRefreshToken();
          if (newToken) {
            const userData = await fetchCurrentUser();
            setUser(userData);
            return;
          }
        } catch {
          // Both access & refresh token failed
        }
      }
      console.warn('Stored token is invalid or expired. Clearing token state.');
      clearStoredTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    initAuth();

    const handleAuthExpired = () => {
      setUser(null);
      clearStoredTokens();
    };

    window.addEventListener('atm:auth-expired', handleAuthExpired);
    return () => {
      window.removeEventListener('atm:auth-expired', handleAuthExpired);
    };
  }, []);

  const login = async (credentials: LoginCredentials) => {
    await loginUser(credentials);
    const userData = await fetchCurrentUser();
    setUser(userData);
    setLoginModalOpen(false);
  };

  const register = async (payload: RegisterPayload) => {
    await registerUser(payload);
    // Automatically log in newly registered user
    await loginUser({ email: payload.email, password: payload.password });
    const userData = await fetchCurrentUser();
    setUser(userData);
    setLoginModalOpen(false);
  };

  const logout = () => {
    clearStoredTokens();
    setUser(null);
  };

  const openLoginModal = () => setLoginModalOpen(true);
  const closeLoginModal = () => setLoginModalOpen(false);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        loginModalOpen,
        login,
        register,
        logout,
        openLoginModal,
        closeLoginModal,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

