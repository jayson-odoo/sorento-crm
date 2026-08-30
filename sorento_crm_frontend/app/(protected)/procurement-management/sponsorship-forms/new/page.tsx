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

export default function NewSponsorshipFormPage() {
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
        <PurchaseRequestForm
          defaultRequestType="sponsorship_form"
          successRedirectUrl="/procurement-management/sponsorship-forms"
        />
      </div>
    </Container>
  );
}
