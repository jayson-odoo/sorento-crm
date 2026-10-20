'use client';

import * as React from 'react';
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
import type { SalesOrderSplitBy } from '../../_shared/types/projectSalesOrder.types';

const SPLIT_BY_OPTIONS: { value: SalesOrderSplitBy; label: string }[] = [
  { value: 'area', label: 'Schedule area' },
  { value: 'delivery_date', label: 'Delivery date' },
  { value: 'delivery_month', label: 'Delivery month' },
];

/**
 * Build drafts from one PO plus one CONFIRMED delivery schedule version.
 *
 * One dialog (PM-SIMPLIFY AC-B1). Opened from the PO page, `poId` and `scheduleVersionId`
 * are the page's, so split by is the only field. What a rebuild replaces is said in the
 * dialog itself rather than in a second confirm. Only confirmed versions are offered: the
 * server refuses an unconfirmed one (D3).
 */
export function SalesOrderBuildDialog({
  projectId,
  poId: fixedPoId,
  scheduleVersionId: fixedScheduleVersionId,
  onDone,
  onBuild,
  building,
}: {
  projectId: string;
  poId?: string;
  scheduleVersionId?: string;
  onDone: () => void;
  onBuild: (input: {
    poId: string;
    scheduleVersionId: string;
    splitBy: SalesOrderSplitBy;
  }) => Promise<unknown>;
  building: boolean;
}) {
  const purchaseOrders = usePurchaseOrders(projectId);
  const fixed = Boolean(fixedPoId && fixedScheduleVersionId);
  const [poId, setPoId] = React.useState(fixedPoId ?? '');
  const [scheduleVersionId, setScheduleVersionId] = React.useState(fixedScheduleVersionId ?? '');
  const [splitBy, setSplitBy] = React.useState<SalesOrderSplitBy>('area');

  const scheduleVersions = useScheduleVersions(poId || undefined);

  const poOptions = (purchaseOrders.data ?? []).map((po) => ({
    value: po.id,
    label: po.po_number || 'Unnumbered PO',
    description: [po.issuing_party_name, po.po_date ? formatDateInMalaysia(po.po_date) : null]
      .filter(Boolean)
      .join(' · '),
  }));

  const versionOptions = (scheduleVersions.data ?? [])
    .filter((version) => Boolean(version.confirmed_at))
    .map((version) => ({
      value: version.id,
      label: version.revision_label || `Version ${version.version_no}`,
      description: [
        version.issuer_party_label,
        version.schedule_date ? formatDateInMalaysia(version.schedule_date) : null,
      ]
        .filter(Boolean)
        .join(' · '),
    }));

  const chosenPo = (purchaseOrders.data ?? []).find((po) => po.id === poId);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Build sales orders</DialogTitle>
          <DialogDescription>
            {fixed && chosenPo
              ? `From ${chosenPo.po_number} and its confirmed delivery schedule. `
              : 'From one purchase order and its confirmed delivery schedule. '}
            Drafts built earlier from the same pair are replaced, including any regrouping
            done on them. Published sales orders are left alone.
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
          {!fixed && (
          <>
          <div className="space-y-1.5">
            <Label htmlFor="build-po">
              Purchase order <span className="text-destructive">*</span>
            </Label>
            {purchaseOrders.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading purchase orders…</p>
            ) : poOptions.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2.5 text-sm text-muted-foreground">
                No purchase order on this project yet. Upload or record one on the Orders
                tab first.
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
                This PO has no confirmed delivery schedule yet. Upload and confirm one on the
                PO's Deliveries tab.
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
          </>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="build-split-by">
              Split by <span className="text-destructive">*</span>
            </Label>
            <SearchableSelect
              id="build-split-by"
              value={splitBy}
              onChange={(next) => setSplitBy((next || 'area') as SalesOrderSplitBy)}
              options={SPLIT_BY_OPTIONS}
              placeholder="Select how to split"
            />
          </div>
        </DialogBody>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!poId || !scheduleVersionId || building}
            onClick={async () => {
              try {
                await onBuild({ poId, scheduleVersionId, splitBy });
              } catch {
                // The mutation already toasted the reason; the dialog stays open.
                return;
              }
              onDone();
            }}
          >
            {building ? 'Building…' : 'Build sales orders'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
