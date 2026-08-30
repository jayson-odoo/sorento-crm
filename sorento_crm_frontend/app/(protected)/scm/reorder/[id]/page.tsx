import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ReorderPlanView } from '../components/ReorderPlanView';

export const metadata: Metadata = {
  title: 'Plan',
  description: 'One reorder plan: decide each product, then confirm the lot.',
};

export default async function ReorderPlanPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <PageHeader title="Reorder Planning" />
      </Container>

      <Container width="fluid">
        <ReorderPlanView runId={id} />
      </Container>
    </RequireAccess>
  );
}
