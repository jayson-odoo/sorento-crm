import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import PolicyDetail from '../../components/PolicyDetail';

export const metadata: Metadata = {
  title: 'Warranty Policy',
};

export default async function WarrantyPolicyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Container>
      <PageHeader
        title="Warranty Policy"
        actions={<BackToList listPath="/after-sales/warranty" label="Back to warranty configuration" />}
      />
      <div className="mt-6">
        <PolicyDetail policyId={id} />
      </div>
    </Container>
  );
}
