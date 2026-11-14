import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WarrantyConfigView from './components/WarrantyConfigView';

export const metadata: Metadata = {
  title: 'Warranty Configuration',
};

export default function WarrantyConfigPage() {
  return (
    <>
      <Container>
        <PageHeader title="Warranty Configuration" />
      </Container>
      <Container>
        <WarrantyConfigView />
      </Container>
    </>
  );
}
