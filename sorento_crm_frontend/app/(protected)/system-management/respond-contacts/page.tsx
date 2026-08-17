import { Metadata } from 'next';
import Link from 'next/link';
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
import RespondContactsOutboundList from './components/RespondContactsOutboundList';

export const metadata: Metadata = {
  title: 'Respond Contacts',
  description: 'Control which Respond.io contacts the system may send WhatsApp messages to.',
};

export default function RespondContactsPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Respond Contacts</ToolbarTitle>
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
          <ToolbarActions>
            {/* The two surfaces are not duplicates: this one reaches EVERY contact
                (including those with no agent grant) and holds the kill switch. */}
            <Link
              href="/user-management/contact-access-agents"
              className="text-sm text-muted-foreground hover:text-primary underline underline-offset-4"
            >
              Per-contact switches are also on Internal Users
            </Link>
          </ToolbarActions>
        </Toolbar>
      </Container>
      <Container>
        <RespondContactsOutboundList />
      </Container>
    </>
  );
}
