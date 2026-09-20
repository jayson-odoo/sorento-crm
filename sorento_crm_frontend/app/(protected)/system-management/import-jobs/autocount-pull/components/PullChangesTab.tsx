'use client';

import { useState } from 'react';
import { ImportJobRowsCard } from '../../components/ImportJobRowsCard';

export interface PullChangesTabProps {
  jobId: string;
}

/**
 * "What Confirm will do" - the preview task writes one `import_job_rows` row per
 * created/changed/failed/left-out record (products) or not-applied/skipped/negative/quantity
 * -change row (stock) onto the PULL job itself, so this is the same rows card every other
 * importer uses, filters, search, CSV export and all (AC-RV-2). No pull-specific fetching here.
 *
 * E1 (small-fix track, fix round 2): `ImportJobRowsCard`'s outcome/code filters are CONTROLLED
 * props - the generic job page owns that state itself because its own Outcome breakdown card
 * drives it too. A pull job has no such card, so this tab owns the (much smaller) two pieces
 * of state itself instead, or the Outcome/Reason selects sit there doing nothing.
 */
export function PullChangesTab({ jobId }: PullChangesTabProps) {
  const [outcomeFilter, setOutcomeFilter] = useState('');
  const [codeFilter, setCodeFilter] = useState('');
  return (
    <ImportJobRowsCard
      jobId={jobId}
      outcomeFilter={outcomeFilter}
      codeFilter={codeFilter}
      onChangeOutcome={setOutcomeFilter}
      onChangeCode={setCodeFilter}
    />
  );
}

export default PullChangesTab;
