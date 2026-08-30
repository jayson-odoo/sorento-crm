'use client';

/**
 * The Complaints action set (D15).
 *
 * These are the actions that need nothing but the row: its id, and whether it has
 * been voided. Both the list row's "..." and the record's gear render them, in
 * this order and behind this one delete gate, so an action cannot be reachable
 * from one surface and missing from the other.
 *
 * The record's gear carries MORE than this, and deliberately: escalate, the SLA
 * extension, reassign, the two edits, close, the reply and the view link all read
 * the fetched complaint, its live SLA tracker or its handling lock. A list row
 * holds none of that, so those verbs stay where the data is.
 *
 * The builder is a plain function, not a hook, because a DataGrid `cell` renderer
 * is called during its parent's render rather than mounted as a component of its
 * own - a hook in there is a hook called in a loop. The list owns the one delete
 * dialog and the export mutation; the record page's hook below owns its own.
 */

import { useState } from 'react';
import { FileDown, Trash2 } from 'lucide-react';

import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import ComplaintDeleteDialog from './components/ComplaintDeleteDialog';
import { useExportComplaintPdf } from './hooks/useComplaints';
import type { Complaint } from './types/complaint.types';

/** A voided complaint is kept for the audit trail, so it is never deletable. */
export function isComplaintVoided(complaint: Pick<Complaint, 'status'>): boolean {
  return (complaint.status ?? '').trim().toLowerCase() === 'voided';
}

export interface ComplaintActionsInput {
  /** True while the PDF export is in flight, so the item reads as busy. */
  isExporting?: boolean;
  onExport: (complaintId: string) => void;
  onDeleteRequested: () => void;
  /**
   * Off while the record page has a form action inside its grace window
   * (`formAction.ctasDisabled`), which a delete would undo underneath it.
   *
   * The LIST leaves it on. That state is per-record, in flight, and served by a
   * form-action read the list payload does not carry; asking for it per row would
   * be one request per row to hide a menu item for the few seconds a countdown
   * runs. The record applies the stricter gate the moment it is opened, and the
   * server refuses the delete either way.
   */
  canDelete?: boolean;
}

/** The items themselves. One order, one gate, both surfaces. */
export function complaintActions(
  complaint: Pick<Complaint, 'id' | 'status'>,
  { isExporting, onExport, onDeleteRequested, canDelete = true }: ComplaintActionsInput,
): RecordAction[] {
  const actions: RecordAction[] = [
    {
      key: 'complaint.export_pdf',
      label: 'Download PDF',
      icon: FileDown,
      disabled: isExporting,
      run: () => onExport(complaint.id),
    },
  ];

  if (canDelete && !isComplaintVoided(complaint)) {
    actions.push({
      key: 'complaint.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      run: onDeleteRequested,
    });
  }

  return actions;
}

export interface UseComplaintActionsOptions {
  /** See `ComplaintActionsInput.canDelete`. */
  canDelete?: boolean;
  /** Where to go once the complaint is gone (the record returns to the list). */
  onDeleted?: () => void;
}

/** The record page's copy: the same items, plus the dialog they need mounted. */
export function useComplaintActions(
  complaint: Complaint | null | undefined,
  { canDelete = true, onDeleted }: UseComplaintActionsOptions = {},
): RecordActionSet {
  const exportPdf = useExportComplaintPdf();
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (!complaint) return { actions: [] };

  return {
    actions: complaintActions(complaint, {
      isExporting: exportPdf.isPending,
      onExport: (id) => exportPdf.mutate(id),
      onDeleteRequested: () => setDeleteOpen(true),
      canDelete,
    }),
    dialogs: (
      <ComplaintDeleteDialog
        open={deleteOpen}
        closeDialog={() => setDeleteOpen(false)}
        complaint={complaint}
        onSuccess={onDeleted}
      />
    ),
  };
}
