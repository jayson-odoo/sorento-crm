'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionForm from '../components/PromotionForm';

export default function NewPromotionPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Promotion"
          actions={
            <Button asChild variant="outline">
              <Link href="/marketing-management/promotions">
                <MoveLeft /> Back to promotions
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <PromotionForm
          onSuccess={() => {
            router.push('/marketing-management/promotions');
          }}
        />
      </Container>
    </>
  );
}
