'use client';

import { useCallback, useEffect, useState } from 'react';
import { Clock, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { toast } from 'sonner';
import {
  clearSlaWaiting,
  setSlaWaiting,
  type SlaWaitingOption,
} from '@/app/(protected)/sla-management/conversation-sla-tracking/services/conversationSLATrackingService';

/**
 * Who this stage is waiting on (AC-M1, AC-M3, AC-M4).
 *
 * Two states, one component. When nothing is waiting it offers the party (required) and
 * the reason (optional) - naming WHO is the mandatory half, because a reason nobody has
 * added to the list yet must not stop somebody recording that the case is sitting on a
 * plumber. When something IS waiting it reads back the sentence AC-M3 asks for and
 * offers to end the wait.
 *
 * The vocabularies come from `lookup_bindings`, so an admin can add a party or a reason
 * in master data with no release here. The option list is the reason both columns store
 * the option VALUE rather than an id: a bound column is what makes this endpoint work.
 *
 * Setting a wait moves no clock (AC-M2). A genuine deadline move is Extend, and only
 * Extend (AC-M6), which lives in the page's gear menu.
 */
export function SlaWaitingBanner({
  trackingId,
  party,
  partyLabel,
  reason,
  waitingSince,
  overdue,
  onChanged,
}: {
  trackingId: string;
  party?: string | null;
  partyLabel?: string | null;
  reason?: string | null;
  waitingSince?: string | null;
  /** Past its deadline: naming the wait is mandatory before resolve / escalate / extend. */
  overdue?: boolean;
  onChanged?: () => void;
}) {
  const [options, setOptions] = useState<{
    parties: SlaWaitingOption[];
    reasons: SlaWaitingOption[];
  }>({ parties: [], reasons: [] });
  const [draftParty, setDraftParty] = useState('');
  const [draftReason, setDraftReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const loadOptions = useCallback(async () => {
    // Read BY BINDING, not by set key: the binding is the contract the column already
    // declares, so nothing here has to know which set an admin pointed it at. Also the
    // only lookup path `lib/api.ts` rewrites - `/api/lookup/...` is not in its table and
    // 404s against the Next server.
    const read = async (column: string): Promise<SlaWaitingOption[]> => {
      const response = await apiFetch(
        `/api/v1/lookup/by-binding?table=conversation_sla_tracking&column=${column}`,
      );
      if (!response.ok) return [];
      const body = await response.json().catch(() => null);
      const rows = Array.isArray(body?.options) ? body.options : [];
      return rows.map((row: { value: string; label?: string }) => ({
        value: row.value,
        label: row.label || row.value,
      }));
    };
    const [parties, reasons] = await Promise.all([
      read('waiting_on_party'),
      read('waiting_on_reason'),
    ]);
    setOptions({ parties, reasons });
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  useEffect(() => {
    setDraftParty(party ?? '');
    setDraftReason(reason ?? '');
  }, [party, reason]);

  const save = async () => {
    if (!draftParty) return;
    setBusy(true);
    try {
      await setSlaWaiting(trackingId, { party: draftParty, reason: draftReason || null });
      toast.success('Waiting party recorded.');
      setEditing(false);
      onChanged?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to set the waiting party.');
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await clearSlaWaiting(trackingId);
      toast.success('No longer waiting.');
      onChanged?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to clear the waiting party.');
    } finally {
      setBusy(false);
    }
  };

  const isWaiting = !!party;
  const shown = partyLabel || party;

  if (isWaiting && !editing) {
    return (
      <div className="rounded-md border border-amber-300/60 bg-amber-50/60 px-3 py-2 dark:bg-amber-950/20">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex min-w-0 items-center gap-2 text-sm text-amber-800 dark:text-amber-400">
            <Clock className="size-4 shrink-0" />
            <span className="min-w-0 break-words">
              Waiting on <strong>{shown}</strong>
              {waitingSince ? ` since ${formatDateTimeInMalaysia(waitingSince)}` : ''}
              {reason ? ` - ${options.reasons.find((r) => r.value === reason)?.label ?? reason}` : ''}
            </span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => setEditing(true)}>
              Change
            </Button>
            <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={stop}>
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : 'No longer waiting'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!isWaiting && !editing) {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-dashed px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="min-w-0 text-sm text-muted-foreground">
          {overdue
            ? 'Past its deadline. Say who this is waiting on before you resolve, escalate or extend it.'
            : 'Waiting on someone outside this stage?'}
        </p>
        <Button size="sm" variant="outline" className="h-7 shrink-0" onClick={() => setEditing(true)}>
          Record a wait
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-md border px-3 py-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-1.5">
          <label className="text-xs text-muted-foreground">Waiting on</label>
          <SearchableSelect
            value={draftParty}
            onChange={setDraftParty}
            options={options.parties}
            placeholder="Pick a party"
            disabled={busy}
          />
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <label className="text-xs text-muted-foreground">Reason (optional)</label>
          <SearchableSelect
            value={draftReason}
            onChange={setDraftReason}
            options={options.reasons}
            placeholder="Pick a reason"
            disabled={busy}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" className="h-8" disabled={busy || !draftParty} onClick={save}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : 'Save'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-8"
            disabled={busy}
            onClick={() => {
              setEditing(false);
              setDraftParty(party ?? '');
              setDraftReason(reason ?? '');
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
