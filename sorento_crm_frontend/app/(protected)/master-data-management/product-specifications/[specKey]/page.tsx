import { Metadata } from 'next';
import { SpecKeyRecordDetail } from '../components/SpecKeyRecordDetail';

export const metadata: Metadata = {
  title: 'Specification',
  description: 'A specification record - values, words, rules and where it is seen.',
};

export default async function ProductSpecificationRecordPage({
  params,
}: {
  params: Promise<{ specKey: string }>;
}) {
  const { specKey } = await params;

  return <SpecKeyRecordDetail specKey={specKey} />;
}
