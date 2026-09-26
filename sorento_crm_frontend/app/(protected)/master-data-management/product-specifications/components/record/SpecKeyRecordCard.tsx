'use client';

import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader } from '@/components/ui/card';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { specTypeLabel } from '../../lib/specTypeLabel';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/**
 * The record card (AC-S3.7): read-only in both modes, and NOT where the label
 * lives - the page title (`SpecKeyRecordDetail`) shows that once. This card is
 * one type chip and the pager/gear/primary, and nothing else: no code name, no
 * "Built in", no rule count, no "Unit None", no duplicate "Active", no Advanced.
 * The one place the identity fields (Name, Unit, In use) are editable is Details,
 * first in the tab order.
 */
export function SpecKeyRecordCard({
  row,
  mode,
  pagerNode,
  actions,
  pending,
  primary,
}: {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  pagerNode: ReactNode;
  actions: RecordAction[];
  pending: ReactNode;
  primary: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="block py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <Badge variant="secondary" appearance="light" size="sm" shape="circle">
            {specTypeLabel(row.data_type, row.unit)}
          </Badge>

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
