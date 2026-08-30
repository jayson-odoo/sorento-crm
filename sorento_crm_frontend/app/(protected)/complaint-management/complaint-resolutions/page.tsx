import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ComplaintResolutionsList from './components/ComplaintResolutionsList';

export const metadata: Metadata = {
  title: 'Complaint Resolutions',
  description: 'Manage complaint resolution master data.',
};

export default async function ComplaintResolutionsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Resolutions" />
      </Container>

      <Container>
        <ComplaintResolutionsList />
      </Container>
    </>
  );
}
