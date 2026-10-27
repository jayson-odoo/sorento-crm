import { Metadata } from 'next';
import { CataloguePhotosReview } from './components/CataloguePhotosReview';

export const metadata: Metadata = {
  title: 'Catalogue photos',
  description: 'Review the photos read from a catalogue, then attach them to products.',
};

export default async function CataloguePhotosRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CataloguePhotosReview id={id} />;
}
