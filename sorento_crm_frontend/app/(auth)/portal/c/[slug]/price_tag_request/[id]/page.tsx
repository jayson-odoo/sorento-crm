'use client';

import { use } from 'react';
import { PriceTagRequestForm } from '../../../../components/PriceTagRequestForm';

// Trim trailing punctuation WhatsApp's link detection can absorb.
function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}

export default function PortalSlugPriceTagRequestDetailPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id } = use(params);
  return <PriceTagRequestForm requestId={sanitizeId(id)} slug={slug} />;
}
