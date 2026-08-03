import type { NextApiRequest, NextApiResponse } from 'next';
import { forwardResponse, setSessionCookie, userServiceFetch } from '../../../utils/authServer';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') return res.status(405).end();
  const upstream = await userServiceFetch('/v1/auth/login', { method: 'POST', body: JSON.stringify(req.body) });
  if (!upstream.ok) return forwardResponse(upstream, res);
  const session = await upstream.json();
  setSessionCookie(res, session.access_token, session.expires_at);
  return res.status(200).json(session.user);
}
