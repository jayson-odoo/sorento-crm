'use client';

import * as React from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import { usePurchaseOrders } from '../../_shared/hooks/useProjects';
import { useScheduleVersions } from '../../_shared/hooks/useProjectSalesOrders';

/**
 * Build drafts from one PO plus one confirmed delivery schedule version.
 *
 * Two steps, never nested dialogs: pick, then confirm. The confirmation exists because a
 * rebuild replaces the drafts the same pair produced last time, which throws away any hand
 * regrouping done on them.
 */
export function SalesOrderBuildDialog({
  projectId,
  onDone,
  onBuild,
  building,
}: {
  projectId: string;
  onDone: () => void;
  onBuild: (input: { poId: string; scheduleVersionId: string }) => Promise<unknown>;
  building: boolean;
}) {
  const purchaseOrders = usePurchaseOrders(projectId);
  const [poId, setPoId] = React.useState('');
  const [scheduleVersionId, setScheduleVersionId] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);

  const scheduleVersions = useScheduleVersions(poId || undefined);

  const poOptions = (purchaseOrders.data ?? []).map((po) => ({
    value: po.id,
    label: po.po_number || 'Unnumbered PO',
    description: [po.issuing_party_name, po.po_date ? formatDateInMalaysia(po.po_date) : null]
      .filter(Boolean)
      .join(' · '),
  }));

  const versionOptions = (scheduleVersions.data ?? []).map((version) => ({
    value: version.id,
    label: version.revision_label || `Version ${version.version_no}`,
    description: [
      version.issuer_party_label,
      version.schedule_date ? formatDateInMalaysia(version.schedule_date) : null,
      version.confirmed_at ? 'Confirmed' : 'Not confirmed yet',
    ]
      .filter(Boolean)
      .join(' · '),
  }));

  const chosenPo = (purchaseOrders.data ?? []).find((po) => po.id === poId);
  const chosenVersion = (scheduleVersions.data ?? []).find(
    (version) => version.id === scheduleVersionId,
  );

  if (confirming) {
    return (
      <AlertDialog open onOpenChange={(next) => !next && setConfirming(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Build the drafts?</AlertDialogTitle>
            <AlertDialogDescription>
              {`${chosenPo?.po_number ?? 'This PO'} against ${
                chosenVersion?.revision_label || `version ${chosenVersion?.version_no ?? ''}`
              }. Drafts built earlier from the same pair are replaced, including any regrouping done on them. Published sales orders are left alone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={building}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={building}
              onClick={async (event) => {
                event.preventDefault();
                await onBuild({ poId, scheduleVersionId });
                onDone();
              }}
            >
              {building ? 'Building…' : 'Build drafts'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Build sales order drafts</DialogTitle>
          <DialogDescription>
            From one purchase order and the delivery schedule version it is committed
            against.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
          <div className="space-y-1.5">
            <Label htmlFor="build-po">
              Purchase order <span className="text-destructive">*</span>
            </Label>
            {purchaseOrders.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading purchase orders…</p>
            ) : poOptions.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground">
                No purchase order on this project yet. Record one on the Purchase orders tab
                first.
              </p>
            ) : (
              <SearchableSelect
                id="build-po"
                value={poId}
                onChange={(next) => {
                  setPoId(next);
                  setScheduleVersionId('');
                }}
                options={poOptions}
                placeholder="Select a purchase order"
              />
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="build-schedule">
              Delivery schedule version <span className="text-destructive">*</span>
            </Label>
            {!poId ? (
              <p className="text-sm text-muted-foreground">Choose a purchase order first.</p>
            ) : scheduleVersions.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading schedule versions…</p>
            ) : scheduleVersions.isError ? (
              <p className="text-sm text-destructive">
                {scheduleVersions.error instanceof Error
                  ? scheduleVersions.error.message
                  : 'The delivery schedules could not be loaded.'}
              </p>
            ) : versionOptions.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground">
                This PO has no delivery schedule yet. Upload and confirm one on the Delivery
                schedules tab.
              </p>
            ) : (
              <SearchableSelect
                id="build-schedule"
                value={scheduleVersionId}
                onChange={setScheduleVersionId}
                options={versionOptions}
                placeholder="Select a schedule version"
              />
            )}
          </div>
        </DialogBody>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!poId || !scheduleVersionId}
            onClick={() => setConfirming(true)}
          >
            Build drafts
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
