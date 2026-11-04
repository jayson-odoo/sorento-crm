import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { QuotationTemplatesClient } from './components/QuotationTemplatesClient';

export const metadata = { title: 'Quotation Templates' };

export default function Page() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container>
        <PageHeader title="Quotation Templates" />
      </Container>

      <Container>
        <QuotationTemplatesClient />
      </Container>
    </RequireAccess>
  );
}
