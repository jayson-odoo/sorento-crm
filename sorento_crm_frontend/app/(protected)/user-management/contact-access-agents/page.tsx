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
import ContactsList from '../contacts/components/ContactsList';

export const metadata: Metadata = {
  title: 'Internal Users',
  description: 'View internal users.',
};

export default async function ContactAccessAgentsPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Internal Users</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>User Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            {/* The sibling surface: it reaches contacts with no agent grant, and
                holds the all-contacts kill switch. */}
            <Link
              href="/system-management/respond-contacts"
              className="text-sm text-muted-foreground hover:text-primary underline underline-offset-4"
            >
              Every contact and the kill switch: Respond Contacts
            </Link>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <ContactsList />
      </Container>
    </>
  );
}
