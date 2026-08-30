import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import StockInquiriesList from './components/StockInquiriesList';

export const metadata: Metadata = {
  title: 'Stock Inquiries',
  description: 'Manage stock inquiries and lead times',
};

export default function StockInquiriesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Stock Inquiries" />
      </Container>

      <Container>
        <StockInquiriesList />
      </Container>
    </>
  );
}
