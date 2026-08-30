import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AppStoreAdmin from './components/AppStoreAdmin';

export const metadata: Metadata = {
  title: 'App Store',
  description: 'Install and manage application modules for your organization.',
};

export default function AppStorePage() {
  return (
    <>
      <Container>
        <PageHeader title="App Store" />
      </Container>

      <Container className="space-y-6">
        <AppStoreAdmin />
      </Container>
    </>
  );
}
