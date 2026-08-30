import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import PurchaseRequestForm from '../../../purchase-requests/components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'Edit Sponsorship Form',
  description: 'Edit sponsorship form',
};

export default function EditSponsorshipFormPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <EditSponsorshipFormWrapper params={params} />
    </Container>
  );
}

async function EditSponsorshipFormWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <PageHeader
        title="Edit Sponsorship Form"
        actions={
          <Button variant="outline" asChild>
            <Link href={`/procurement-management/sponsorship-forms/${id}`}>
              Cancel
            </Link>
          </Button>
        }
      />
      <div className="mt-6">
        <PurchaseRequestForm
          requestId={id}
          defaultRequestType="sponsorship_form"
          expectedRequestType="sponsorship_form"
          successRedirectUrl={`/procurement-management/sponsorship-forms/${id}`}
        />
      </div>
    </>
  );
}
