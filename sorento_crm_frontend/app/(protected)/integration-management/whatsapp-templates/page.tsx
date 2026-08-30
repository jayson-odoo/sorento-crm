import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import WhatsAppTemplatesView from './components/WhatsAppTemplatesView';

export const metadata: Metadata = {
  title: 'WhatsApp Templates',
  description: 'Sync Respond.io WhatsApp templates and configure auto-send defaults.',
};

export default async function WhatsAppTemplatesPage() {
  return (
    <RequireAccess permission="integration.respond_templates.view">
      <Container>
        <PageHeader title="WhatsApp Templates" />
      </Container>

      <Container className="space-y-5">
        <WhatsAppTemplatesView />
      </Container>
    </RequireAccess>
  );
}
