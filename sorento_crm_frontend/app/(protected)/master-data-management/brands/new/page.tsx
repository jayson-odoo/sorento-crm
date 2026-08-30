'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BrandForm from '../components/BrandForm';

export default function NewBrandPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Brand"
          actions={
            <Button asChild variant="outline">
              <Link href="/master-data-management/brands">
                <MoveLeft /> Back to brands
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <BrandForm
          brandId={undefined}
          onSuccess={() => {
            router.push('/master-data-management/brands');
          }}
        />
      </Container>
    </>
  );
}
