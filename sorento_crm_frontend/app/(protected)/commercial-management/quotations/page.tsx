import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import QuotationsList from './components/QuotationsList';

export const metadata: Metadata = {
  title: 'Quotations',
  description: 'Commercial master quotations.',
};

export default async function QuotationsPage() {
  return (
    <Container className="bg-[#f9fafb] pb-10 pt-6">
      <QuotationsList />
    </Container>
  );
}
