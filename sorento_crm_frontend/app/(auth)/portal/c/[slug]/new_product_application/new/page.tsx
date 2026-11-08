'use client';

import { use } from 'react';
import NewProductApplicationForm from '../../../../components/NewProductApplicationForm';

export default function PortalSlugNewProductApplicationNewPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ stock_inquiry_id?: string }>;
}) {
  const { slug } = use(params);
  const { stock_inquiry_id } = use(searchParams);
  return (
    <NewProductApplicationForm
      slug={slug}
      startFromInquiryId={stock_inquiry_id}
    />
  );
}
