import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ChatbotEntityKindsList from './components/ChatbotEntityKindsList';

export const metadata: Metadata = {
  title: 'Entity kinds',
  description: 'What the chatbot resolves a name against, per kind.',
};

export default function ChatbotEntityKindsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Entity kinds" />
      </Container>

      <Container>
        <ChatbotEntityKindsList />
      </Container>
    </>
  );
}
