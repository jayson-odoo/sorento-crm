import RequireAccess from '@/app/components/common/RequireAccess';
import { SeriesDetailClient } from './components/SeriesDetailClient';

export const metadata = { title: 'Series' };

export default async function Page({
  params,
}: {
  params: Promise<{ seriesId: string }>;
}) {
  const { seriesId } = await params;
  return (
    <RequireAccess permission="projects.types.view">
      <SeriesDetailClient seriesId={seriesId} />
    </RequireAccess>
  );
}
