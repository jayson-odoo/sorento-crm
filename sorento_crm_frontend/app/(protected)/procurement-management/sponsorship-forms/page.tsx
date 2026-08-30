import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PurchaseRequestsList from '../purchase-requests/components/PurchaseRequestsList';

export const metadata: Metadata = {
  title: 'Sponsorship Forms',
  description: 'Sponsorship forms',
};

export default function SponsorshipFormsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Sponsorship Forms" />
      </Container>

      <Container>
        <PurchaseRequestsList
          requestType="sponsorship_form"
          basePath="/procurement-management/sponsorship-forms"
          reportPermission="procurement.sponsorship_forms.report"
        />
      </Container>
    </>
  );
}
