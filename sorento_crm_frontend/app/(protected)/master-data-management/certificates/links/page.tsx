import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CertificateLinksList from '../components/CertificateLinksList';

export const metadata: Metadata = {
  title: 'Certificate Links to Check',
  description: 'Certificate-product links checked against the certificate text.',
};

export default async function CertificateLinksPage() {
  return (
    <>
      <Container>
        <PageHeader title="Certificate Links to Check" />
      </Container>

      <Container>
        <CertificateLinksList />
      </Container>
    </>
  );
}
