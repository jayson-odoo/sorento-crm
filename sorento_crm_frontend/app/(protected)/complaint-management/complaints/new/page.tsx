'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ComplaintForm from '../components/ComplaintForm';

export default function NewComplaintPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Complaint"
          actions={
            <Button asChild variant="outline">
              <Link href="/complaint-management/complaints">
                <MoveLeft /> Back to complaints
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <ComplaintForm
          onSuccess={() => {
            router.push('/complaint-management/complaints');
          }}
        />
      </Container>
    </>
  );
}
