import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CostPriceUploadsList from './components/CostPriceUploadsList';

export const metadata: Metadata = {
  title: 'Cost Price Uploads',
  description: "A supplier's price list, reviewed and applied as dated cost lists.",
};

export default function CostPriceUploadsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Cost Price Uploads" />
      </Container>

      <Container>
        <CostPriceUploadsList />
      </Container>
    </>
  );
}
