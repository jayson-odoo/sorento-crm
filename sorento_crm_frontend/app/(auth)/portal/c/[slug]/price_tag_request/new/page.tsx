'use client';

import { use } from 'react';
import { PriceTagRequestForm } from '../../../../components/PriceTagRequestForm';

export default function PortalSlugPriceTagRequestNewPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return <PriceTagRequestForm slug={slug} />;
}
