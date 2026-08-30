import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CertificateDetail from '../components/CertificateDetail';
import BackToList from '@/components/common/BackToList';

export const metadata: Metadata = {
  title: 'Certificate Details',
  description: 'View a certificate, its revisions and its covered products.',
};

export default async function CertificateDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Container>
      <PageHeader
        title="Certificate"
        actions={
          <BackToList
            listPath="/master-data-management/certificates"
            label="Back to certificates"
          />
        }
      />
      <div className="mt-6">
        <CertificateDetail certificateId={id} />
      </div>
    </Container>
  );
}
