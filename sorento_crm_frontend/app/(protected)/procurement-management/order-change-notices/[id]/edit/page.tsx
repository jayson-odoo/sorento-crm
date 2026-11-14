'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderChangeNoticeForm from '../../components/OrderChangeNoticeForm';

export default function EditOrderChangeNoticePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Container>
      <PageHeader title="Edit Order Change Notice" />
      <div className="mt-6">
        <OrderChangeNoticeForm ocnId={id} />
      </div>
    </Container>
  );
}
