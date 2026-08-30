'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CampaignForm from '../components/CampaignForm';

export default function NewCampaignPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Campaign"
          actions={
            <Button asChild variant="outline">
              <Link href="/marketing-management/campaigns">
                <MoveLeft /> Back to campaigns
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <CampaignForm
          onSuccess={() => {
            router.push('/marketing-management/campaigns');
          }}
        />
      </Container>
    </>
  );
}
