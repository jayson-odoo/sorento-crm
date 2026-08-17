import { SeriesDetailClient } from './components/SeriesDetailClient';

export const metadata = { title: 'Series' };

export default async function Page({
  params,
}: {
  params: Promise<{ seriesId: string }>;
}) {
  const { seriesId } = await params;
  return <SeriesDetailClient seriesId={seriesId} />;
}
