import { PromptDetail } from '../components/PromptDetail';

export const metadata = {
  title: 'Edit prompt',
};

export default async function PromptDetailPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return <PromptDetail name={name} />;
}
