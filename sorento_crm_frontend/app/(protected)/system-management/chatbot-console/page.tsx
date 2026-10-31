import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ChatbotConsole, { CHATBOT_CONSOLE_VIEW_PERMISSION } from './components/ChatbotConsole';

export const metadata: Metadata = {
  title: 'Chatbot Console',
  description: 'A dry-run WhatsApp conversation, for testing the bot before it ships.',
};

export default async function ChatbotConsolePage() {
  return (
    <>
      <Container>
        <PageHeader title="Chatbot Console" />
      </Container>

      <Container>
        {/* Sidebar entry is permission-gated, but a deep link is not - without the
            guard a denied user lands on a console whose every call 403s. */}
        <RequireAccess permission={CHATBOT_CONSOLE_VIEW_PERMISSION}>
          <ChatbotConsole />
        </RequireAccess>
      </Container>
    </>
  );
}
