'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  getFormSLATrackers,
  escalateFormTracking,
  type FormSLASourceType,
} from './formSLAService';

/**
 * Manual SLA escalation straight from an entity detail page's actions menu
 * (TCK-28) — no need to open the SLA Tracking tab. Shared across complaint,
 * stock inquiry, purchase request and sponsorship form so the resolve-active-
 * tracker + reason-dialog + escalate flow can't drift between domains.
 *
 * Usage:
 *   const sla = useSlaEscalateAction('stock_inquiry', id);
 *   // in the actions menu:
 *   <DropdownMenuItem disabled={sla.resolving} onClick={sla.openEscalate}>
 *     <ArrowUpCircle className="size-4" />
 *     {sla.resolving ? 'Loading SLA…' : 'Escalate SLA'}
 *   </DropdownMenuItem>
 *   // anywhere in the JSX tree (portal-rendered):
 *   {sla.dialog}
 */
export function useSlaEscalateAction(
  entityType: FormSLASourceType,
  entityId: string,
) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [trackerId, setTrackerId] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [busy, setBusy] = useState(false);

  const openEscalate = useCallback(async () => {
    setResolving(true);
    try {
      const trackers = await getFormSLATrackers(entityType, entityId);
      const active = trackers.filter((t) => !t.is_resolved);
      if (active.length === 0) {
        toast.error('No active SLA tracker to escalate.');
        return;
      }
      // Highest-tier active tracker (closest to / past breach).
      const target = [...active].sort((a, b) => b.current_tier - a.current_tier)[0];
      setTrackerId(target.id);
      setReason('');
      setOpen(true);
    } catch {
      toast.error('Failed to load SLA tracker.');
    } finally {
      setResolving(false);
    }
  }, [entityType, entityId]);

  const confirm = useCallback(async () => {
    if (!trackerId || !reason.trim()) return;
    setBusy(true);
    try {
      const res = await escalateFormTracking(trackerId, reason.trim());
      toast.success(
        res.assigned_to_name
          ? `Escalated to tier ${res.current_tier}, assigned to ${res.assigned_to_name}.`
          : `Escalated to tier ${res.current_tier}.`,
      );
      setOpen(false);
      setTrackerId(null);
      setReason('');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to escalate SLA.');
    } finally {
      setBusy(false);
    }
  }, [trackerId, reason]);

  const dialog = (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Escalate SLA</DialogTitle>
          <DialogDescription>
            Moves the active SLA stage to the next tier and reassigns per policy.
            The new assignee is notified.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          placeholder="Why escalate now?"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={busy || !reason.trim()}>
            {busy ? 'Escalating…' : 'Escalate'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { resolving, openEscalate, dialog };
}
