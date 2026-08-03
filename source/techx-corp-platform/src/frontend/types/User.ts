export interface User {
  id: string;
  email: string;
  username: string;
  status: 'active' | 'disabled' | 'deleted';
  created_at: string;
  updated_at: string;
}

export interface AuthSession {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: User;
}
