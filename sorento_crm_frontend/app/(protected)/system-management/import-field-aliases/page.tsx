import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ImportFieldAliasesList from './components/ImportFieldAliasesList';

export const metadata: Metadata = {
  title: 'Import Column Mappings',
  description: 'Every header a supplier document uses, and the system field it means.',
};

export default function ImportFieldAliasesPage() {
  return (
    <RequireAccess permission="system.import_field_aliases.view">
      <Container>
        <PageHeader title="Import Column Mappings" />
      </Container>

      <Container className="space-y-6">
        <ImportFieldAliasesList />
      </Container>
    </RequireAccess>
  );
}
