import { Metadata } from 'next';
import Link from 'next/link';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ContactsList from '../contacts/components/ContactsList';

export const metadata: Metadata = {
  title: 'Internal Users',
  description: 'View internal users.',
};

export default async function ContactAccessAgentsPage() {
  return (
    <>
      <Container>
        <PageHeader
          title="Internal Users"
          actions={
            <>
              {/* The sibling surface: it reaches contacts with no agent grant, and
                  holds the all-contacts kill switch. */}
              <Link
                href="/system-management/respond-contacts"
                className="text-sm text-muted-foreground hover:text-primary underline underline-offset-4"
              >
                Every contact and the kill switch: Respond Contacts
              </Link>
            </>
          }
        />
      </Container>

      <Container>
        <ContactsList />
      </Container>
    </>
  );
}
