import type { NextApiRequest, NextApiResponse } from 'next';
import { resolveUser } from '../../../utils/authServer';

const { PRODUCT_REVIEWS_HTTP_ADDR = '' } = process.env;

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'PATCH' && req.method !== 'DELETE') return res.status(405).end();
  const user = await resolveUser(req);
  if (!user) return res.status(401).json({ detail: 'Authentication required' });
  const upstream = await fetch(`${PRODUCT_REVIEWS_HTTP_ADDR}/v1/reviews/${encodeURIComponent(req.query.reviewId as string)}`, {
    method: req.method,
    headers: { 'content-type': 'application/json', 'x-user-id': user.id, 'x-username': user.username },
    body: req.method === 'PATCH' ? JSON.stringify(req.body) : undefined,
  });
  res.setHeader('content-type', 'application/json');
  return res.status(upstream.status).send(await upstream.text());
}
