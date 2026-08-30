'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import StockInquiryForm from '../../components/StockInquiryForm';

export default function EditStockInquiryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Stock Inquiry"
          actions={
            <Button asChild variant="outline">
              <Link href={`/procurement-management/stock-inquiries/${id}`}>
                <MoveLeft /> Back to stock inquiry
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <StockInquiryForm
          inquiryId={id}
          onSuccess={() => {
            router.push(`/procurement-management/stock-inquiries/${id}`);
          }}
        />
      </Container>
    </>
  );
}
