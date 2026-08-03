import type { NextApiRequest, NextApiResponse } from 'next';

const { USER_SERVICE_ADDR = '' } = process.env;
export const SESSION_COOKIE = 'xbrain_session';

export const getSessionToken = (req: NextApiRequest) => req.cookies[SESSION_COOKIE];

export const authHeaders = (req: NextApiRequest): Record<string, string> => {
  const token = getSessionToken(req);
  return token ? { authorization: `Bearer ${token}` } : {};
};

export const userServiceFetch = (path: string, init?: RequestInit) =>
  fetch(`${USER_SERVICE_ADDR}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers || {}) },
  });

export const forwardResponse = async (upstream: Response, res: NextApiResponse) => {
  const text = await upstream.text();
  if (!text) return res.status(upstream.status).end();
  res.status(upstream.status).setHeader('content-type', upstream.headers.get('content-type') || 'application/json');
  return res.send(text);
};

export const setSessionCookie = (res: NextApiResponse, token: string, expiresAt: string) => {
  const secure = process.env.COOKIE_SECURE === 'true' ? '; Secure' : '';
  res.setHeader(
    'Set-Cookie',
    `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Expires=${new Date(expiresAt).toUTCString()}${secure}`
  );
};

export const clearSessionCookie = (res: NextApiResponse) =>
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`);

export const resolveUser = async (req: NextApiRequest) => {
  const response = await userServiceFetch('/v1/users/me', { headers: authHeaders(req) });
  return response.ok ? response.json() : null;
};
