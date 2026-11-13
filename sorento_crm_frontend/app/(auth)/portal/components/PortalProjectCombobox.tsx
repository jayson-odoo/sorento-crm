'use client';

import { AsyncCombobox } from './AsyncCombobox';
import type { ProjectLookupItem } from '../lib/portal-client';
import { useSubmissionClient } from '../lib/submission-client';
import { projectCodeLabel } from '@/app/(protected)/project-sales/_shared/lib/projectCode';
import { projectDisplayName } from '@/app/(protected)/project-sales/_shared/lib/projectName';

/** "code - title", the way every project picker names a project. */
export const portalProjectLabel = (o: ProjectLookupItem) =>
  `${projectCodeLabel(o)} - ${projectDisplayName(o)}`;

/**
 * The portal's "Registered project" picker: only the contact's own companies' approved projects
 * (`/lookups/projects`, `projects_for_contact`), picked and never typed, each row naming its
 * company. One component for every portal form that links a project (sponsorship form, stock
 * inquiry, complaint, purchase request, sample request, new product application).
 */
export function PortalProjectCombobox({
  id,
  value,
  displayValue,
  onChange,
  disabled,
  placeholder = 'Search your registered projects...',
  ariaLabel,
}: {
  id?: string;
  value: string;
  /** The saved project's label, so a reloaded form shows it and never the id. */
  displayValue?: string;
  /** The picked id ('' when cleared) and its label. */
  onChange: (projectId: string, label: string) => void;
  disabled?: boolean;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const client = useSubmissionClient();
  return (
    <AsyncCombobox<ProjectLookupItem>
      id={id}
      ariaLabel={ariaLabel}
      value={value}
      displayValue={displayValue}
      onChange={(v, item) => onChange(v, item ? portalProjectLabel(item) : '')}
      fetchOptions={(q) => client.lookupProjects(q)}
      optionValue={(o) => o.id}
      optionLabel={portalProjectLabel}
      // A registered project is picked, never typed: the column is a UUID FK, so free text
      // would reach the server as an id and fail there instead of here.
      allowFreeText={false}
      // The company on every row (AC-F4a): a contact mapped to two of them cannot otherwise
      // tell two similarly-named phases apart.
      optionMeta={(o) => o.company_name ?? ''}
      placeholder={placeholder}
      disabled={disabled}
    />
  );
}
