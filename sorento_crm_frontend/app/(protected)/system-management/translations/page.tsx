import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TranslationsList from './components/TranslationsList';

export const metadata: Metadata = {
  title: 'Translations',
  description: 'The Chinese-English translation memory supplier documents read from.',
};

export default async function TranslationsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Translations" />
      </Container>

      <Container>
        <TranslationsList />
      </Container>
    </>
  );
}
