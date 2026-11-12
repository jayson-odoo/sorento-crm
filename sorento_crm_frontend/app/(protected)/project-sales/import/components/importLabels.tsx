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

/** Plain words for a reason code; the server's own label set, mirrored for the filter. */
export const CODE_LABELS: Record<string, string> = {
  project_and_po_created: 'Project and PO created',
  po_added: 'PO added to the project',
  no_project_name: 'No project name',
  placeholder: 'Numbered but empty',
  other_year: 'Not a 2026 PS number',
  cancelled: 'Cancelled',
  mapped_skip: 'Set to skip',
  project_unmapped: 'Project not linked yet',
  customer_unmapped: 'Customer not linked yet',
  developer_unmapped: 'Developer not linked yet',
  customer_conflict: 'Sales order customer differs from the linked customer',
  customer_same_shop_so_used: 'Sales order customer used (same shop)',
  developer_conflict: 'Rows of one new project name different developers',
  developer_exists: 'A party with this developer name already exists',
  registration_lock: 'Same developer and title as an existing project',
  po_number_taken: 'PO number already on this project',
  so_on_other_project: 'Sales order already on another project',
  ps_duplicate_in_file: 'PS number appears twice in the file',
  ps_duplicate_in_crm: 'PS number is on two POs already',
  changed_in_file: 'Differs from the CRM, left as it is',
  so_linked: 'Sales order linked',
  so_not_synced: 'Sales order not synced yet',
  po_number_numeric: 'PO number was a number cell',
  date_other_year: 'PO date not in 2026',
  date_other_month: 'PO date in another month than its sheet',
  owner_defaulted: 'Owner set to the importing user',
  clash_check_skipped: 'Duplicate check skipped (linked by a person)',
  row_error: 'Row could not be written',
};

export function codeLabel(code: string): string {
  return CODE_LABELS[code] ?? code.replace(/_/g, ' ');
}

/** The Values tab a blocking code sends the reader to (AC-PI-47). */
export function kindForCode(code: string): ProjectImportKind | null {
  if (code.startsWith('customer_')) return 'customer';
  if (code.startsWith('project_') || code === 'registration_lock' || code === 'po_number_taken') {
    return 'project';
  }
  if (code.startsWith('developer_')) return 'developer';
  return null;
}
