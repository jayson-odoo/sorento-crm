import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import UserList from './components/user-list';

export const metadata: Metadata = {
  title: 'Administrative Users',
  description: 'Manage administrative users.',
};

export default async function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Administrative Users" />
      </Container>

      <Container>
        <UserList />
      </Container>
    </>
  );
}
