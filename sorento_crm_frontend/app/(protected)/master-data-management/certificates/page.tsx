import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CertificatesList from './components/CertificatesList';

export const metadata: Metadata = {
  title: 'Certificates',
  description: 'Product certification register.',
};

export default async function CertificatesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Certificates" />
      </Container>

      <Container>
        <CertificatesList />
      </Container>
    </>
  );
}
