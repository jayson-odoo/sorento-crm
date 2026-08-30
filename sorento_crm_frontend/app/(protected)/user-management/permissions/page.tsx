import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PermissionList from './components/permission-list';

export const metadata: Metadata = {
  title: 'Permissions',
  description: 'Manage user permissions.',
};

export default async function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Permissions" />
      </Container>
      <Container>
        <PermissionList />
      </Container>
    </>
  );
}
