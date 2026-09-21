import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ChatbotDomainsList from './components/ChatbotDomainsList';

export const metadata: Metadata = {
  title: 'Chatbot Domains',
  description: 'What the chatbot can answer, per domain.',
};

export default function ChatbotDomainsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Chatbot Domains" />
      </Container>

      <Container>
        <ChatbotDomainsList />
      </Container>
    </>
  );
}
