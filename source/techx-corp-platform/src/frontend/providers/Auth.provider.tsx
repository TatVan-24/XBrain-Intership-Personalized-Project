import { createContext, useContext, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { User } from '../types/User';

type Credentials = { email: string; password: string; username?: string };
type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (credentials: Credentials) => Promise<void>;
  register: (credentials: Credentials) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({} as AuthContextValue);
const callAuth = async (path: string, body?: object) => {
  const response = await fetch(`/api/auth/${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Authentication request failed');
  return data;
};

export const useAuth = () => useContext(AuthContext);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const { data: user = null, isLoading } = useQuery<User | null>({
    queryKey: ['currentUser'],
    queryFn: async () => {
      const response = await fetch('/api/auth/me');
      return response.ok ? response.json() : null;
    },
    retry: false,
  });
  const authenticate = async (path: 'login' | 'register', credentials: Credentials) => {
    const nextUser = await callAuth(path, credentials);
    queryClient.setQueryData(['currentUser'], nextUser);
  };
  const value = useMemo(() => ({
    user,
    loading: isLoading,
    login: (credentials: Credentials) => authenticate('login', credentials),
    register: (credentials: Credentials) => authenticate('register', credentials),
    logout: async () => {
      await callAuth('logout', {});
      queryClient.setQueryData(['currentUser'], null);
    },
  }), [user, isLoading, queryClient]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
