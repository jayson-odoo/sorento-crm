import { PriceFloorDetailClient } from './components/PriceFloorDetailClient';

export const metadata = { title: 'Price Floor' };

export default async function Page({ params }: { params: Promise<{ ruleId: string }> }) {
  const { ruleId } = await params;
  return <PriceFloorDetailClient ruleId={ruleId} />;
}
