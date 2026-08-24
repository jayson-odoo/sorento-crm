import RequireAccess from '@/app/components/common/RequireAccess';
import { PriceFloorDetailClient } from './components/PriceFloorDetailClient';

export const metadata = { title: 'Price Floor' };

export default async function Page({ params }: { params: Promise<{ ruleId: string }> }) {
  const { ruleId } = await params;
  return (
    <RequireAccess permission="projects.types.view">
      <PriceFloorDetailClient ruleId={ruleId} />
    </RequireAccess>
  );
}
