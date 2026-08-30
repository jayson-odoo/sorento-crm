import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SmartLinkageList from './components/SmartLinkageList';

export const metadata: Metadata = {
  title: 'Smart Linkage',
  description: 'View integration logs for attachments.',
};

export default async function SmartLinkagePage() {
  return (
    <>
      <Container>
        <PageHeader title="Smart Linkage" />
      </Container>

      <Container>
        <SmartLinkageList />
      </Container>
    </>
  );
}
