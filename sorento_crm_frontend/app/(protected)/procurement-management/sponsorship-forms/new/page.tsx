import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import PurchaseRequestForm from '../../purchase-requests/components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'New Sponsorship Form',
  description: 'Create a sponsorship form',
};

export default async function NewSponsorshipFormPage({
  searchParams,
}: {
  searchParams: Promise<{ project_id?: string }>;
}) {
  const { project_id } = await searchParams;
  return (
    <Container>
      <PageHeader
        title="New Sponsorship Form"
        actions={
          <Button variant="outline" asChild>
            <Link href="/procurement-management/sponsorship-forms">Cancel</Link>
          </Button>
        }
      />
      <div className="mt-6">
        {/* A salesperson's own form reads ?from= / ?revise= (useSearchParams). */}
        <Suspense fallback={null}>
          <PurchaseRequestForm
            defaultRequestType="sponsorship_form"
            defaultProjectId={project_id}
            successRedirectUrl="/procurement-management/sponsorship-forms"
          />
        </Suspense>
      </div>
    </Container>
  );
}
