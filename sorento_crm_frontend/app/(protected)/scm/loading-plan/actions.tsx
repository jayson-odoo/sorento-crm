'use client';

/**
 * The loading plan action set (S1, D15): Send to supplier, Change cut-off, Cancel plan,
 * Delete plan, and the record-only extras (View uploaded list, Refresh matching, Refresh
 * suggestion, Copy link, the two downloads), shaped exactly like `user-management/users/
 * actions.tsx`.
 *
 * Cancel and Delete are common to every surface, so their disabled reasons ("Already
 * cancelled", "Sent plans are cancelled, not deleted") and their deferred countdown
 * (`useDeferredAction`, D7) live in exactly one place, here. The record-only items need
 * context only the record page holds - the built lines, the notices query, the cut-off
 * dialog - so the caller hands each one over pre-built as `{ disabled?, disabledReason?,
 * run }`: present it and it joins the menu in the order the plan names (AC-A2); leave it
 * out and it does not. That is why the list row, which supplies only `send`, ends up with
 * AC-A1's three items (Send to supplier, Cancel plan, separator, Delete plan) while the
 * record's gear, which supplies all of them, gets the full ten - one definition, two
 * surfaces, never a second place for Cancel or Delete to drift.
 */

import { useRouter } from 'next/navigation';
import {
  Ban,
  CalendarDays,
  Download,
  Eye,
  FileText,
  Link2,
  RefreshCw,
  Send,
  Trash2,
} from 'lucide-react';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import type { LoadingPlanRecord } from '../services/fulfilmentService';

/** What a record-only (or row-only) item needs beyond its label and icon, which this hook owns. */
type ActionInput = Pick<RecordAction, 'disabled' | 'disabledReason' | 'run' | 'confirmLabel'>;

export interface UseLoadingPlanActionsOptions {
  /** The record page leaves the record on a committed delete (there is nothing left to view). */
  onDeleted?: () => void;
  /** Clears whatever was typed since the last Save - a cancelled plan is read-only. */
  onCancelled?: () => void;
  /** `inline` hands the countdown back as `pending` for the record's gear area (D7); `toast`
   *  (the list row) puts it over the list instead. */
  surface?: 'inline' | 'toast';
  /** Opens the Send dialog - a row navigates to the record and opens it there; the record
   *  opens it in place. Every caller supplies this (AC-A1 and AC-A2 both list it). */
  send?: ActionInput;
  /** Only present when the plan has a stored copy of the supplier's own file. */
  viewUploadedList?: ActionInput;
  refreshMatching?: ActionInput;
  refreshSuggestion?: ActionInput;
  /** `confirmLabel` defaults to "Copied" - the tick IS the confirmation (S7-05). */
  copyLink?: ActionInput;
  downloadXlsx?: ActionInput;
  downloadPdf?: ActionInput;
  changeCutOff?: ActionInput;
}

export function useLoadingPlanActions(
  plan: LoadingPlanRecord | null | undefined,
  options: UseLoadingPlanActionsOptions = {},
): RecordActionSet {
  const {
    onDeleted,
    onCancelled,
    surface = 'inline',
    send,
    viewUploadedList,
    refreshMatching,
    refreshSuggestion,
    copyLink,
    downloadXlsx,
    downloadPdf,
    changeCutOff,
  } = options;

  const subject = plan?.supplier_name || 'this plan';

  // Cancel: the plan stops being worked on and the supplier's live link stops answering, but
  // asks nothing first (D7) - the countdown is the confirmation.
  const cancellation = useDeferredAction({
    actionKey: 'loading_plan.cancel',
    entityType: 'loading_plan',
    entityId: plan?.id,
    verb: 'Cancelling',
    subject,
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Plan cancelled. The supplier link no longer works.',
    invalidateKeys: [
      ['scm-loading-plans'],
      ['scm', 'fulfilment', 'container-request', plan?.id],
    ],
    onCommitted: onCancelled,
  });

  // Delete: refused by the server once a notice has gone out - the same rule the disabled
  // reason states up front.
  const deletion = useDeferredAction({
    actionKey: 'loading_plan.delete',
    entityType: 'loading_plan',
    entityId: plan?.id,
    verb: 'Deleting',
    subject,
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Plan deleted',
    invalidateKeys: [['scm-loading-plans']],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!plan) return { actions, dialogs: null, pending: null };

  if (viewUploadedList) {
    actions.push({
      key: 'loading_plan.view_uploaded_list',
      label: 'View uploaded list',
      icon: Eye,
      ...viewUploadedList,
    });
  }
  if (refreshMatching) {
    actions.push({
      key: 'loading_plan.refresh_matching',
      label: 'Refresh matching',
      icon: RefreshCw,
      ...refreshMatching,
    });
  }
  if (refreshSuggestion) {
    actions.push({
      key: 'loading_plan.refresh_suggestion',
      label: 'Refresh suggestion',
      icon: RefreshCw,
      ...refreshSuggestion,
    });
  }
  if (copyLink) {
    actions.push({
      key: 'loading_plan.copy_link',
      label: 'Copy link',
      icon: Link2,
      confirmLabel: 'Copied',
      ...copyLink,
    });
  }
  if (downloadXlsx) {
    actions.push({
      key: 'loading_plan.download_xlsx',
      label: 'Download XLSX',
      icon: Download,
      ...downloadXlsx,
    });
  }
  if (downloadPdf) {
    actions.push({
      key: 'loading_plan.download_pdf',
      label: 'Download PDF',
      icon: FileText,
      ...downloadPdf,
    });
  }
  if (send) {
    actions.push({ key: 'loading_plan.send', label: 'Send to supplier', icon: Send, ...send });
  }
  if (changeCutOff) {
    actions.push({
      key: 'loading_plan.change_cut_off',
      label: 'Change cut-off',
      icon: CalendarDays,
      ...changeCutOff,
    });
  }

  actions.push({
    key: 'loading_plan.cancel',
    label: 'Cancel plan',
    icon: Ban,
    disabled: plan.status === 'cancelled' || cancellation.isPending || cancellation.isBlocked,
    disabledReason: plan.status === 'cancelled' ? 'Already cancelled' : undefined,
    run: () => cancellation.start(),
  });

  actions.push({
    key: 'loading_plan.delete',
    label: 'Delete plan',
    icon: Trash2,
    kind: 'destructive',
    disabled: !!plan.sent_at || deletion.isPending || deletion.isBlocked,
    disabledReason: plan.sent_at ? 'Sent plans are cancelled, not deleted' : undefined,
    run: () => deletion.start(),
  });

  return {
    actions,
    dialogs: null,
    // A record on its way out has one thing to offer, and it is Cancel or Delete - whichever
    // is actually parked. Null on the `toast` surface, where the toast carries the countdown.
    pending: surface === 'inline' ? (deletion.countdown ?? cancellation.countdown) : null,
  };
}

/**
 * The list row's "..." cell (D15).
 *
 * Supplies only `send` (a navigation, not the dialog itself - a row has no built lines to
 * hand the dialog), so the shared hook above hands back exactly AC-A1's three items.
 */
export function LoadingPlanRowActions({ plan }: { plan: LoadingPlanRecord }) {
  const router = useRouter();
  const { actions } = useLoadingPlanActions(plan, {
    surface: 'toast',
    send: { run: () => router.push(`/scm/loading-plan/${plan.id}?send=1`) },
  });

  if (actions.length === 0) return null;

  return <RowActionsMenu actions={actions} ariaLabel="loading plan" />;
}

export default useLoadingPlanActions;
