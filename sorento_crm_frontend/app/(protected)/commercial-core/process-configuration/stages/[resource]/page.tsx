import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import ConfigStagesList from '../../_components/ConfigStagesList';
import type { ConfigStageResource } from '../../services/configStageService';

const TITLES: Record<ConfigStageResource, string> = {
  'tender-stages': 'Tender pipeline stages',
  'master-quotation-stages': 'Master quotation stages',
  'task-statuses': 'Task statuses',
};

function isResource(s: string): s is ConfigStageResource {
  return s === 'tender-stages' || s === 'master-quotation-stages' || s === 'task-statuses';
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ resource: string }>;
}): Promise<Metadata> {
  const { resource } = await params;
  if (!isResource(resource)) return { title: 'Process configuration' };
  return { title: TITLES[resource] };
}

export default async function ConfigStagesPage({ params }: { params: Promise<{ resource: string }> }) {
  const { resource } = await params;
  if (!isResource(resource)) notFound();
  const basePath = `/commercial-core/process-configuration/stages/${resource}`;
  return <ConfigStagesList resource={resource} title={TITLES[resource]} basePath={basePath} />;
}
