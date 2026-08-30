import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProformaInvoicesView from './components/ProformaInvoicesView';

export const metadata: Metadata = {
  title: 'Proforma Invoices',
  description: 'The supplier priced documents held on file, by supplier.',
};

export default function ProformaInvoicesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Proforma Invoices" />
      </Container>

      <Container>
        <ProformaInvoicesView />
      </Container>
    </>
  );
}
