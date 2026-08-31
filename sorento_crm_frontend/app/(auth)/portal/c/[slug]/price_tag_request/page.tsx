'use client';

import { use } from 'react';
import { PriceTagRequestList } from '../../../components/PriceTagRequestList';

export default function PortalSlugPriceTagRequestListPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return <PriceTagRequestList slug={slug} />;
}
