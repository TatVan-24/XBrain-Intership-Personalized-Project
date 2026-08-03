import type { NextApiRequest, NextApiResponse } from 'next';
import { authHeaders, clearSessionCookie, forwardResponse, userServiceFetch } from '../../../utils/authServer';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') return res.status(405).end();
  const upstream = await userServiceFetch('/v1/auth/logout', { method: 'POST', headers: authHeaders(req) });
  clearSessionCookie(res);
  return upstream.ok ? res.status(204).end() : forwardResponse(upstream, res);
}
