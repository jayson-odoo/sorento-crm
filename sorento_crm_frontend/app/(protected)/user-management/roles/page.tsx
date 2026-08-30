import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RoleList from './components/role-list';

export const metadata: Metadata = {
  title: 'Roles',
  description: 'Manage user roles.',
};

export default async function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Roles" />
      </Container>
      <Container>
        <RoleList />
      </Container>
    </>
  );
}
