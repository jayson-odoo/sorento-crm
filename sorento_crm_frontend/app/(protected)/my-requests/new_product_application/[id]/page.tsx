'use client';

import { use } from 'react';
import NewProductApplicationForm from '@/app/(auth)/portal/components/NewProductApplicationForm';
import { MySlug, sanitizeId } from '../../MySlug';

export default function MyRequestsNewProductApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <MySlug>
      {(slug) => <NewProductApplicationForm applicationId={sanitizeId(id)} slug={slug} />}
    </MySlug>
  );
}
