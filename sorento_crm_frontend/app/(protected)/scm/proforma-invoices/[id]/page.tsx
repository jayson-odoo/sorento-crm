import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { ProformaInvoiceDetail } from './components/ProformaInvoiceDetail';

export const metadata: Metadata = {
  title: 'Proforma Invoice',
  description: 'Proforma invoice detail - header and priced lines.',
};

export default async function ProformaInvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Container>
        <PageHeader
          title="Proforma Invoice"
          actions={
            <BackToList listPath="/scm/proforma-invoices" label="Back to proforma invoices" />
          }
        />
      </Container>

      <Container>
        <ProformaInvoiceDetail id={id} />
      </Container>
    </>
  );
}
