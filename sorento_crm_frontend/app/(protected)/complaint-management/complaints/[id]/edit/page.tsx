'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ComplaintForm from '../../components/ComplaintForm';

export default function EditComplaintPage({
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
          title="Edit Complaint"
          actions={
            <Button asChild variant="outline">
              <Link href={`/complaint-management/complaints/${id}`}>
                <MoveLeft /> Back to complaint
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <ComplaintForm
          complaintId={id}
          onSuccess={() => {
            router.push(`/complaint-management/complaints/${id}`);
          }}
        />
      </Container>
    </>
  );
}
