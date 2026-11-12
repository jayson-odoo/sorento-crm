'use client';

import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { searchProjectsForLink } from '@/app/(protected)/complaint-management/complaints/services/complaintService';

/**
 * The office-side "Registered project" picker: one approved project, searched by code or title,
 * clearable. One component for every form that links a record to a project (purchase request,
 * sponsorship form, complaint, sample request, stock inquiry, new product application), so the
 * pickers cannot drift. The server checks the pick again (`assert_linkable_project`).
 */
export function RegisteredProjectSelect({
  id,
  value,
  onChange,
  onOptionChange,
  selectedOption,
  disabled,
  emptyMessage = 'No project matches that. Leave it empty if it was never registered.',
  'aria-label': ariaLabel,
}: {
  id?: string;
  value: string | null | undefined;
  /** The picked project id, or null when cleared. */
  onChange: (projectId: string | null) => void;
  onOptionChange?: (option: SearchableSelectOption | null) => void;
  /** The saved project as "code - title", so a reloaded form shows it and never the id. */
  selectedOption?: SearchableSelectOption;
  disabled?: boolean;
  emptyMessage?: string;
  'aria-label'?: string;
}) {
  return (
    // `contain: inline-size`: the control takes its cell's width and never sizes the cell from a
    // long title, so a form never scrolls sideways and the clear button stays on screen.
    <div className="w-full min-w-0 [contain:inline-size]">
      <SearchableSelect
        id={id}
        value={value || ''}
        onChange={(next) => onChange(next || null)}
        onOptionChange={onOptionChange}
        selectedOption={selectedOption}
        fetchOptions={(query, pageIndex) => searchProjectsForLink(query, pageIndex + 1)}
        paginated
        pageSize={25}
        clearable
        truncateTriggerLabel
        triggerClassName="w-full"
        disabled={disabled}
        aria-label={ariaLabel}
        placeholder="Search a project by code or title"
        emptyMessage={emptyMessage}
        // AC-C3a: one line per project, code + title cut with "...", the full text on hover.
        renderOption={(opt) => (
          <span className="min-w-0 flex-1 truncate" title={opt.label}>
            {opt.label}
          </span>
        )}
      />
    </div>
  );
}

/** "code - title" for a saved link, the label the picker shows before any search. */
export function registeredProjectOption(
  id: string | null | undefined,
  code: string | null | undefined,
  title: string | null | undefined,
): SearchableSelectOption | undefined {
  if (!id) return undefined;
  return { value: id, label: [code, title].filter(Boolean).join(' - ') || 'Linked project' };
}
