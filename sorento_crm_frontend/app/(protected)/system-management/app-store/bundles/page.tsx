import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ModuleBundlesAdmin from '../components/ModuleBundlesAdmin';

export const metadata: Metadata = {
  title: 'Module bundles',
  description: 'Define App Store install presets (module bundles).',
};

export default function ModuleBundlesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Module bundles" />
      </Container>

      <Container className="space-y-6">
        <ModuleBundlesAdmin />
      </Container>
    </>
  );
}
