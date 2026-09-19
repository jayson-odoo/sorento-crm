'use client';

import { ImportJobRowsCard } from '../../components/ImportJobRowsCard';

export interface PullChangesTabProps {
  jobId: string;
}

/**
 * "What Confirm will do" - the preview task writes one `import_job_rows` row per
 * created/changed/failed/left-out record (products) or not-applied/skipped/negative/quantity
 * -change row (stock) onto the PULL job itself, so this is the same rows card every other
 * importer uses, filters, search, CSV export and all (AC-RV-2). No pull-specific fetching here.
 */
export function PullChangesTab({ jobId }: PullChangesTabProps) {
  return <ImportJobRowsCard jobId={jobId} />;
}

export default PullChangesTab;
