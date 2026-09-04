import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { TagSizesList } from './components/TagSizesList';

export const metadata: Metadata = {
  title: 'Tag Sizes',
  description: 'Manage saved price tag sizes offered in every request.',
};

export default function TagSizesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Tag Sizes" />
      </Container>

      <Container>
        <TagSizesList />
      </Container>
    </>
  );
}
