'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import FormForm from '../../components/FormForm';

export default function EditFormPage({
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
          title="Edit Form"
          actions={
            <Button asChild variant="outline">
              <Link href={`/forms-management/forms/${id}`}>
                <MoveLeft /> Back to form
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <FormForm
          formId={id}
          onSuccess={() => {
            router.push(`/forms-management/forms/${id}`);
          }}
        />
      </Container>
    </>
  );
}
