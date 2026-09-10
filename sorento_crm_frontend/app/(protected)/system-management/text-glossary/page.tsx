import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import TextGlossaryList from './components/TextGlossaryList';

export const metadata: Metadata = {
  title: 'Text Glossary',
  description: 'Every supplier-document word an operator has typed the English for.',
};

export default function TextGlossaryPage() {
  return (
    <RequireAccess permission="system.text_glossary.view">
      <Container>
        <PageHeader title="Text Glossary" />
      </Container>

      <Container className="space-y-6">
        <TextGlossaryList />
      </Container>
    </RequireAccess>
  );
}
