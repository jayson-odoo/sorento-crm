import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SeriesListClient } from './components/SeriesListClient';

/**
 * Series, on their own page.
 *
 * Two things this deliberately does NOT have, both removed on the client's instruction: a
 * sentence under the title explaining what a series is for, and a second row of buttons under
 * the section heading. Their rule is that a screen needing explanation has already failed, and
 * the controls belong inline in the one standard toolbar - which is where `DataGridListToolbar`
 * puts them, and why the users list has no stray button row.
 */
export const metadata = { title: 'Series' };

export default function Page() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container>
        <PageHeader title="Series" />
      </Container>

      <Container>
        <SeriesListClient />
      </Container>
    </RequireAccess>
  );
}
