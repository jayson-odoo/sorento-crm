import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { NonCancellableListClient } from './components/NonCancellableListClient';

export const metadata = { title: 'Non-cancellable Items' };

export default function Page() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container>
        <PageHeader title="Non-cancellable Items" />
      </Container>

      <Container>
        <NonCancellableListClient />
      </Container>
    </RequireAccess>
  );
}
