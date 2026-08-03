import type { NextApiRequest, NextApiResponse } from 'next';
import { authHeaders, forwardResponse, userServiceFetch } from '../../../utils/authServer';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') return res.status(405).end();
  const upstream = await userServiceFetch('/v1/users/me', { headers: authHeaders(req) });
  return forwardResponse(upstream, res);
}
