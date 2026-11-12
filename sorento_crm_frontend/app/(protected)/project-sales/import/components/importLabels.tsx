'use client';

import { Badge } from '@/components/ui/badge';
import type {
  ProjectImportKind,
  ProjectImportOutcome,
  ProjectImportStatus,
} from '../../_shared/types/projectImport.types';

export const STATUS_LABELS: Record<ProjectImportStatus, string> = {
  draft: 'Draft',
  previewed: 'Previewed',
  importing: 'Importing',
  imported: 'Imported',
  reverted: 'Reverted',
};

const STATUS_VARIANTS: Record<ProjectImportStatus, 'secondary' | 'info' | 'warning' | 'success' | 'outline'> = {
  draft: 'secondary',
  previewed: 'info',
  importing: 'warning',
  imported: 'success',
  reverted: 'outline',
};

export function RunStatusBadge({ status }: { status: ProjectImportStatus }) {
  return (
    <Badge variant={STATUS_VARIANTS[status] ?? 'secondary'} appearance="light">
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}

export const OUTCOME_LABELS: Record<ProjectImportOutcome, string> = {
  created: 'Will create',
  updated: 'Updated',
  unchanged: 'Already imported',
  skipped: 'Skipped',
  needs_review: 'Needs review',
  error: 'Errors',
};

/** Row labels (one row), next to the tile labels (a count) above. */
export const OUTCOME_ROW_LABELS: Record<ProjectImportOutcome, string> = {
  created: 'Create',
  updated: 'Update',
  unchanged: 'Already imported',
  skipped: 'Skipped',
  needs_review: 'Needs review',
  error: 'Error',
};

export const KIND_TABS: { kind: ProjectImportKind; label: string }[] = [
  { kind: 'customer', label: 'Customers' },
  { kind: 'project', label: 'Projects' },
  { kind: 'developer', label: 'Developers' },
  { kind: 'person', label: 'People' },
];

/** The Values tab a blocking code sends the reader to (AC-PI-47). */
export function kindForCode(code: string): ProjectImportKind | null {
  if (code.startsWith('customer_')) return 'customer';
  if (code.startsWith('project_') || code === 'registration_lock' || code === 'po_number_taken') {
    return 'project';
  }
  if (code.startsWith('developer_')) return 'developer';
  return null;
}
