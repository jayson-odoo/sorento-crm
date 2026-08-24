'use client';

import { use } from 'react';
import { PriceTagRequestForm } from '../../components/PriceTagRequestForm';

export default function PortalPriceTagRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <PriceTagRequestForm requestId={id} />;
}
