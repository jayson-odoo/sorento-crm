'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionForm from '../../components/PromotionForm';

export default function EditPromotionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Promotion"
          actions={
            <Button asChild variant="outline">
              <Link href={`/marketing-management/promotions/${id}`}>
                <MoveLeft /> Back to promotion
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <PromotionForm
          promotionId={id}
          onSuccess={() => {
            router.push(`/marketing-management/promotions/${id}`);
          }}
        />
      </Container>
    </>
  );
}
