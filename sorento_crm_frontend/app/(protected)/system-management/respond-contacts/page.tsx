import { Metadata } from 'next';
import Link from 'next/link';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RespondContactsOutboundList from './components/RespondContactsOutboundList';

export const metadata: Metadata = {
  title: 'Respond Contacts',
  description: 'Control which Respond.io contacts the system may send WhatsApp messages to.',
};

export default function RespondContactsPage() {
  return (
    <>
      <Container>
        <PageHeader
          title="Respond Contacts"
          actions={
            <>
              {/* The two surfaces are not duplicates: this one reaches EVERY contact
                  (including those with no agent grant) and holds the kill switch. */}
              <Link
                href="/user-management/contact-access-agents"
                className="text-sm text-muted-foreground hover:text-primary underline underline-offset-4"
              >
                Per-contact switches are also on Internal Users
              </Link>
            </>
          }
        />
      </Container>
      <Container>
        <RespondContactsOutboundList />
      </Container>
    </>
  );
}
