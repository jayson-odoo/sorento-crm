'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import UOMForm from '../components/UOMForm';

export default function NewUOMPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Unit of Measure"
          actions={
            <Button asChild variant="outline">
              <Link href="/master-data-management/units-of-measure">
                <MoveLeft /> Back to UOMs
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <UOMForm
          uomId={undefined}
          onSuccess={() => {
            router.push('/master-data-management/units-of-measure');
          }}
        />
      </Container>
    </>
  );
}
