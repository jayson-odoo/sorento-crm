import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import UOMList from './components/UOMList';

export const metadata: Metadata = {
  title: 'Units of Measure',
  description: 'Manage units of measure.',
};

export default async function UOMPage() {
  return (
    <>
      <Container>
        <PageHeader title="Units of Measure" />
      </Container>

      <Container>
        <UOMList />
      </Container>
    </>
  );
}
