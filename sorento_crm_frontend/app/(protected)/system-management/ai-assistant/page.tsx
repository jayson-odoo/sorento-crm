import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AIAssistantSettingsForm from './components/AIAssistantSettingsForm';
import TraceSettingsCard from './components/TraceSettingsCard';

export const metadata: Metadata = {
  title: 'AI assistant',
  description: 'Configure AI assistant model, system prompt, and tools.',
};

export default function AIAssistantPage() {
  return (
    <>
      <Container>
        <PageHeader title="AI assistant" />
      </Container>
      <Container className="space-y-4">
        <AIAssistantSettingsForm />
        <TraceSettingsCard />
      </Container>
    </>
  );
}
