'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BrandForm from '../../components/BrandForm';

export default function EditBrandPage({
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
          title="Edit Brand"
          actions={
            <Button asChild variant="outline">
              <Link href={`/master-data-management/brands/${id}`}>
                <MoveLeft /> Back to brand
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <BrandForm
          brandId={id}
          onSuccess={() => {
            router.push(`/master-data-management/brands/${id}`);
          }}
        />
      </Container>
    </>
  );
}
