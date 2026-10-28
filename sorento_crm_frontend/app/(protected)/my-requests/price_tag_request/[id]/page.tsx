'use client';

import { use } from 'react';
import { PriceTagRequestForm } from '@/app/(auth)/portal/components/PriceTagRequestForm';
import { MySlug, sanitizeId } from '../../MySlug';

export default function MyRequestsPriceTagDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <MySlug>{(slug) => <PriceTagRequestForm requestId={sanitizeId(id)} slug={slug} />}</MySlug>;
}
