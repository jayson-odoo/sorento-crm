import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ConversationsInbox, {
  CONVERSATIONS_VIEW_PERMISSION,
} from './components/ConversationsInbox';

export const metadata: Metadata = {
  title: 'Conversations',
  description: 'Every WhatsApp conversation, readable by the whole team.',
};

export default async function ConversationsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Conversations" />
      </Container>

      <Container>
        {/* The sidebar entry is permission-gated, but a deep link is not: without
            the guard a denied user would land on an inbox whose every call 403s. */}
        <RequireAccess permission={CONVERSATIONS_VIEW_PERMISSION}>
          <ConversationsInbox />
        </RequireAccess>
      </Container>
    </>
  );
}
