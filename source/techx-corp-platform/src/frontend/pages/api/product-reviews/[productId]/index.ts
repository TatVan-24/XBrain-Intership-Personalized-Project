// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../../../utils/telemetry/InstrumentationMiddleware';
import { resolveUser } from '../../../../utils/authServer';

const { PRODUCT_REVIEWS_HTTP_ADDR = '' } = process.env;

const handler = async (req: NextApiRequest, res: NextApiResponse) => {
    const { method, query } = req;

    switch (method) {
        case 'GET': {
            const { productId = '', limit = '5', offset = '0' } = query;

            const params = new URLSearchParams({ limit: limit as string, offset: offset as string });
            const upstream = await fetch(`${PRODUCT_REVIEWS_HTTP_ADDR}/v1/products/${encodeURIComponent(productId as string)}/reviews?${params}`);
            res.setHeader('content-type', 'application/json');
            return res.status(upstream.status).send(await upstream.text());
        }

        case 'POST': {
            const user = await resolveUser(req);
            if (!user) return res.status(401).json({ detail: 'Authentication required' });
            const upstream = await fetch(`${PRODUCT_REVIEWS_HTTP_ADDR}/v1/products/${encodeURIComponent(query.productId as string)}/reviews`, {
                method: 'POST',
                headers: { 'content-type': 'application/json', 'x-user-id': user.id, 'x-username': user.username },
                body: JSON.stringify(req.body),
            });
            res.setHeader('content-type', 'application/json');
            return res.status(upstream.status).send(await upstream.text());
        }

        default: {
            return res.status(405).send('');
        }
    }
};

export default InstrumentationMiddleware(handler);
