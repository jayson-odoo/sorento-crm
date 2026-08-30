import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RespondWorkspacesAdmin from './components/RespondWorkspacesAdmin';

export const metadata: Metadata = {
  title: 'Respond.io Workspaces',
  description: 'Manage Respond.io workspaces (name, space ID, API key, base URL, default).',
};

export default function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Respond.io Workspaces" />
      </Container>
      <Container>
        <RespondWorkspacesAdmin />
      </Container>
    </>
  );
}
