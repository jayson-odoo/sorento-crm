import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PaymentTermList from './components/PaymentTermList';

export const metadata: Metadata = {
  title: 'Payment Terms',
  description: 'AutoCount payment terms.',
};

export default async function PaymentTermsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Payment Terms" />
      </Container>

      <Container>
        <PaymentTermList />
      </Container>
    </>
  );
}
