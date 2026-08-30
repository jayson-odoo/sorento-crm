'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import StockInquiryForm from '../components/StockInquiryForm';

export default function NewStockInquiryPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Stock Inquiry"
          actions={
            <Button asChild variant="outline">
              <Link href="/procurement-management/stock-inquiries">
                <MoveLeft /> Back to stock inquiries
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <StockInquiryForm
          onSuccess={() => {
            router.push('/procurement-management/stock-inquiries');
          }}
        />
      </Container>
    </>
  );
}
