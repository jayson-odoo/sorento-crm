import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { PromptsList } from './components/PromptsList';

export const metadata: Metadata = {
  title: 'AI assistant prompts',
  description: 'Versioned, editable registry of every prompt the AI assistant uses.',
};

export default function AIAssistantPromptsPage() {
  return (
    <>
      <Container>
        <PageHeader title="AI Assistant Prompts" />
      </Container>
      <Container className="space-y-4">
        <PromptsList />
      </Container>
    </>
  );
}
