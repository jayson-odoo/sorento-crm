'use client';

/**
 * SetCompanyDialog - the ONE dialog for `Set company…` (PLAN-shared-brand-attachments
 * R4, R22-R25). Shared by:
 * - the drive page's `Action` dropdown and row context menu (files and folders).
 * - the Files listing's `Set company (n)` bulk action.
 * - the detail popup's `Company` field `Edit` affordance (one file, single id).
 *
 * The dialog itself never calls the backend. Set company is reversible (R22), so
 * it is not a confirmation - `Apply` parks one deferred action per selected file
 * (`attachment.set_company`) and folder (`attachment_directory.set_company`)
 * through the shipped grace-window engine and closes; the pending toast (with
 * Cancel) and the commit toast come from `useDeferredBulkAction`.
 */
import { useEffect, useId, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useCompany } from '@/app/providers/CompanyProvider';
import { useDeferredBulkAction } from '@/hooks/useDeferredBulkAction';

/**
 * `Shared` reads as company_id = null everywhere the value leaves this dialog,
 * and as `company=shared` on the drive/files list filters (AC-E1) - one
 * sentinel for both, so a real company id (a UUID) never collides with it.
 */
export const SHARED_COMPANY_VALUE = 'shared';

/** "3 folders, 12 files" / "1 folder" / "5 files" - the reader's words for a mixed selection. */
function describeCounts(folderCount: number, fileCount: number): string {
  const parts: string[] = [];
  if (folderCount > 0) parts.push(`${folderCount} folder${folderCount === 1 ? '' : 's'}`);
  if (fileCount > 0) parts.push(`${fileCount} file${fileCount === 1 ? '' : 's'}`);
  return parts.join(', ');
}

export interface SetCompanyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fileIds: string[];
  folderIds: string[];
  /** Called once the batch is parked (before the grace window lapses) - where a list drops its selection. */
  onApplied?: () => void;
}

export default function SetCompanyDialog({
  open,
  onOpenChange,
  fileIds,
  folderIds,
  onApplied,
}: SetCompanyDialogProps) {
  const { grants } = useCompany();
  const [companyValue, setCompanyValue] = useState('');
  const triggerId = useId();

  useEffect(() => {
    if (open) setCompanyValue('');
  }, [open]);

  const totalCount = fileIds.length + folderIds.length;

  const describe = useMemo(() => {
    const counted = describeCounts(folderIds.length, fileIds.length);
    return (count: number) =>
      count === totalCount && counted
        ? counted
        : `${count} item${count === 1 ? '' : 's'}`;
  }, [fileIds.length, folderIds.length, totalCount]);

  const setCompany = useDeferredBulkAction({
    actionKey: 'attachment.set_company',
    entityType: 'attachment',
    verb: 'Setting company',
    // Only reached by the hook's own "Nothing could be X" refusal sentence
    // (finishText below covers every other path) - "company set" there reads
    // as "Nothing could be company set."
    pastVerb: 'updated',
    describe,
    invalidateKeys: [
      ['drive-contents'],
      ['attachments'],
      ['attachment-metadata'],
      ['attachment-directories-tree'],
    ],
    onStarted: onApplied,
    finishText: {
      allCommitted: (count) => `Company set: ${describe(count)}`,
      allFailed: (count) => `Could not set company for ${describe(count)}.`,
      partial: (committed, failed) =>
        `Company set for ${describe(committed)}; ${failed} could not be.`,
    },
  });

  const options = [
    ...grants.map((company) => ({ value: company.id, label: company.name })),
    { value: SHARED_COMPANY_VALUE, label: 'Shared' },
  ];

  const handleApply = () => {
    if (!companyValue || totalCount === 0 || setCompany.isStarting) return;
    const companyId = companyValue === SHARED_COMPANY_VALUE ? null : companyValue;
    const targets = [
      ...fileIds.map((id) => ({ id, payload: { company_id: companyId } })),
      ...folderIds.map((id) => ({
        id,
        payload: { company_id: companyId },
        actionKey: 'attachment_directory.set_company',
        entityType: 'attachment_directory',
      })),
    ];
    setCompany.run(targets);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md"
        onOpenAutoFocus={(e) => {
          // Focused on open (AC-F4): the trigger is the one control in this
          // dialog. Radix's own default (the content wrapper) is a no-op for
          // this purpose, so this claims focus in the SAME frame instead of
          // racing it with a timeout.
          e.preventDefault();
          document.getElementById(triggerId)?.focus();
        }}
        onKeyDown={(e) => {
          // Only the CLOSED trigger, with a value already chosen, applies on
          // Enter. An Enter fired from inside the open popover (the search
          // input, a highlighted row) must reach cmdk's own handling - React
          // portals still bubble through this react subtree even though the
          // popover renders outside it in the DOM, so this has to be
          // narrowed to the trigger button itself or every keyboard pick
          // would be swallowed before it can select anything.
          const target = e.target as HTMLElement;
          if (
            e.key === 'Enter' &&
            companyValue &&
            target.getAttribute('role') === 'combobox'
          ) {
            e.preventDefault();
            handleApply();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Set company</DialogTitle>
          <DialogDescription>{describeCounts(folderIds.length, fileIds.length) || '-'}</DialogDescription>
        </DialogHeader>

        <div className="py-2 space-y-2">
          <SearchableSelect
            id={triggerId}
            value={companyValue}
            onChange={setCompanyValue}
            options={options}
            placeholder="Select company"
            disabled={setCompany.isStarting}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={setCompany.isStarting}>
            Cancel
          </Button>
          <Button onClick={handleApply} disabled={!companyValue || setCompany.isStarting || totalCount === 0}>
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
