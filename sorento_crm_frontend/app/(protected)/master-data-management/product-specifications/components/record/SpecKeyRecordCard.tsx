'use client';

import type { ReactNode } from 'react';
import { Card, CardHeader } from '@/components/ui/card';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';

/**
 * The record card (AC-S3.7): read-only in both modes, and NOT where the label or
 * the type chip lives - the page header (`SpecKeyRecordDetail`) shows both once
 * (review round 2, N-7). This card is the pager/gear/primary, and nothing else: no
 * code name, no "Built in", no rule count, no "Unit None", no duplicate "Active",
 * no Advanced.
 * The one place the identity fields (Name, Unit, In use) are editable is Details,
 * first in the tab order.
 */
export function SpecKeyRecordCard({
  mode,
  pagerNode,
  actions,
  pending,
  primary,
}: {
  mode: 'view' | 'edit';
  pagerNode: ReactNode;
  actions: RecordAction[];
  pending: ReactNode;
  primary: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="block py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-end">
          {/* An edit session states ONE intent: Save or Cancel. Nav and Delete act on
              the record as it is STORED, so both are disabled while editing rather
              than unmounted (UAC B.2 exception): a client-side route change fires no
              `beforeunload`, and unmounting them would let a click through to drop
              the draft with no warning. */}
          <DetailActions
            pagerNode={pagerNode}
            actions={actions}
            pendingAction={pending}
            primary={primary}
            gearLabel="Specification options"
            disabled={mode === 'edit'}
          />
        </div>
      </CardHeader>
    </Card>
  );
}

export default SpecKeyRecordCard;
