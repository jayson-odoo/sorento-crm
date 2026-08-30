'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import FormForm from '../components/FormForm';

export default function NewFormPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Form"
          actions={
            <Button asChild variant="outline">
              <Link href="/forms-management/forms">
                <MoveLeft /> Back to forms
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <FormForm
          onSuccess={() => {
            router.push('/forms-management/forms');
          }}
        />
      </Container>
    </>
  );
}
