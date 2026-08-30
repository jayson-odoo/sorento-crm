import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import MessageSnippetsList from './components/MessageSnippetsList';

export const metadata: Metadata = {
  title: 'Message Snippets',
  description: 'Canned replies offered in the conversation composer.',
};

export default async function MessageSnippetsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Message Snippets" />
      </Container>

      <Container>
        <MessageSnippetsList />
      </Container>
    </>
  );
}
