import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import IncomingContainersView from './components/IncomingContainersView';

export const metadata: Metadata = {
  title: 'Incoming Containers',
  description: 'Read the packing list, then decide what each container draws down.',
};

export default function IncomingContainersPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container>
        {/* The menu entry is retired (R2) - the tree-derived trail would otherwise match
            Supply Chain's Dashboard leaf (`/scm`, a bare prefix of this path) as a wrong
            ancestor. `crumbs` is the documented escape hatch for "the sidebar names
            nothing here" (PageHeader.inventory.test.ts S5-02), so this stays title-only. */}
        <PageHeader
          title="Incoming Containers"
          crumbs={[{ title: 'Incoming Containers' }]}
        />
      </Container>

      <Container>
        <IncomingContainersView />
      </Container>
    </RequireAccess>
  );
}
