import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
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
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>WhatsApp Templates</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>System Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container className="space-y-5">
        <WhatsAppTemplatesView />
      </Container>
    </RequireAccess>
  );
}
