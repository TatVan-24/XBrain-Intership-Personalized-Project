import type { NextApiRequest, NextApiResponse } from 'next';
import { forwardResponse, setSessionCookie, userServiceFetch } from '../../../utils/authServer';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') return res.status(405).end();
  const registered = await userServiceFetch('/v1/auth/register', { method: 'POST', body: JSON.stringify(req.body) });
  if (!registered.ok) return forwardResponse(registered, res);
  const loggedIn = await userServiceFetch('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: req.body.email, password: req.body.password }),
  });
  if (!loggedIn.ok) return forwardResponse(loggedIn, res);
  const session = await loggedIn.json();
  setSessionCookie(res, session.access_token, session.expires_at);
  return res.status(201).json(session.user);
}
