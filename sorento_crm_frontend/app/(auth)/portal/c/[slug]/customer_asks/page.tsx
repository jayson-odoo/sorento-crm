'use client';

import { use } from 'react';
import { CustomerAsksList } from '../../../components/CustomerAsksList';

export default function PortalSlugCustomerAsksPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return <CustomerAsksList slug={slug} />;
}
