import { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ReorderRunsGrid } from './components/ReorderRunsGrid';

export const metadata: Metadata = {
  title: 'Reorder Planning',
  description: 'Every reorder plan, and the one button that starts a new one.',
};

export default async function ReorderPlansPage({
  searchParams,
}: {
  searchParams: Promise<{ run?: string; plan?: string }>;
}) {
  const { run, plan } = await searchParams;

  // R1: the plan lives at its own address now. Every `?plan=` link ever copied off the old
  // screen still lands on the right plan - it just arrives at the URL that names it.
  if (plan) redirect(`/scm/reorder/${encodeURIComponent(plan)}`);

  // `?run=1` auto-opens the Start Plan modal (deep-link support; the dashboard's header
  // "Reorder plan" button navigates here without it - M8-B6).
  const autoOpenRun = run === '1';

  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <PageHeader title="Reorder Planning" />
      </Container>

      <Container width="fluid">
        <ReorderRunsGrid autoOpenRun={autoOpenRun} />
      </Container>
    </RequireAccess>
  );
}
