import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import LoadingPlanView from '../components/LoadingPlanView';

export const metadata: Metadata = {
  title: 'Loading Plan',
  description: 'What to ask this supplier for on the next container.',
};

/**
 * One container plan (R5).
 *
 * The toolbar is NOT here: its title is the supplier's name and its right-hand cluster acts on
 * quantities typed in the grid, so it lives inside the client view where both are known.
 */
export default async function LoadingPlanRecordPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <RequireAccess permission="scm.reorder.run">
      <Container>
        <LoadingPlanView planId={id} />
      </Container>
    </RequireAccess>
  );
}
