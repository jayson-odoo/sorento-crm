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
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import ConversationsInbox from './components/ConversationsInbox';

export const metadata: Metadata = {
  title: 'Conversations',
  description: 'Every WhatsApp conversation, readable by the whole team.',
};

export default async function ConversationsPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Conversations</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>SLA Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Conversations</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions></ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <ConversationsInbox />
      </Container>
    </>
  );
}
