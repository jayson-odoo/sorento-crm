import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import AccessSheetImportPage from '../components/AccessSheetImportPage';

export const metadata: Metadata = {
  title: 'Import access sheet',
  description: 'Set dealer contacts access from the Respond contact export.',
};

export default function AccessSheetPage() {
  return (
    <>
      <Container>
        <PageHeader
          title="Import access sheet"
          crumbs={[
            { title: 'Users & Access' },
            { title: 'People' },
            { title: 'Internal Users', path: '/user-management/contact-access-agents' },
            { title: 'Import access sheet' },
          ]}
        />
      </Container>
      <Container>
        <RequireAccess permission="user_management.contacts.edit">
          <AccessSheetImportPage />
        </RequireAccess>
      </Container>
    </>
  );
}
