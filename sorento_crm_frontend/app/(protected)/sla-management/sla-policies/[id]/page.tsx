'use client';

import { use } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SLAPolicyDetail from '../components/SLAPolicyDetail';

export default function SLAPolicyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="SLA Policy"
          actions={
            <Button asChild variant="outline">
              <Link href="/sla-management/sla-policies">
                <MoveLeft /> Back to SLA policies
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <SLAPolicyDetail slaPolicyId={id} />
      </Container>
    </>
  );
}
