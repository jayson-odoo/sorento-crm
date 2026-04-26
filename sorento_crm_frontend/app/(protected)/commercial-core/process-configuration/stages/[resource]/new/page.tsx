import { notFound } from 'next/navigation';
import ConfigStageForm from '../../../_components/ConfigStageForm';
import type { ConfigStageResource } from '../../../services/configStageService';

function isResource(s: string): s is ConfigStageResource {
  return s === 'tender-stages' || s === 'master-quotation-stages' || s === 'task-statuses';
}

export default async function NewConfigStagePage({ params }: { params: Promise<{ resource: string }> }) {
  const { resource } = await params;
  if (!isResource(resource)) notFound();
  const listPath = `/commercial-core/process-configuration/stages/${resource}`;
  return <ConfigStageForm resource={resource} listPath={listPath} />;
}
