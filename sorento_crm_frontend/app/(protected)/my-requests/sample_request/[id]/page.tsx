'use client';

import { use } from 'react';
import SampleRequestForm from '@/app/(auth)/portal/components/SampleRequestForm';
import { MySlug, sanitizeId } from '../../MySlug';

export default function MyRequestsSampleRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <MySlug>{(slug) => <SampleRequestForm requestId={sanitizeId(id)} slug={slug} />}</MySlug>;
}
