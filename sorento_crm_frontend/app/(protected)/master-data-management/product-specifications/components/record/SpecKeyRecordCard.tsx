'use client';

import type { ReactNode } from 'react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { specTypeLabel } from '../../lib/specTypeLabel';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/**
 * The record card (B.1, D15b): read-only in both modes. Label, the slug, type and
 * source pills, unit and Active are facts here - the one place they are editable
 * is the Header tab, first in the tab order. `DetailActions` in the design-language
 * order: pager, gear, primary.
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
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-lg">{row.label}</CardTitle>
              <Badge variant="secondary" appearance="light" size="sm" shape="circle">
                {specTypeLabel(row.data_type)}
              </Badge>
              <Badge
                variant={row.source === 'user' ? 'primary' : 'secondary'}
                appearance="light"
                size="sm"
                shape="circle"
              >
                {row.source === 'user' ? 'User' : 'Seed'}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <code className="truncate">{row.spec_key}</code>
              <span className="flex items-center gap-1.5">
                Unit
                <span>{row.unit || 'None'}</span>
              </span>
              <span className="flex items-center gap-1.5">
                Active
                <Badge
                  variant={row.is_active ? 'success' : 'secondary'}
                  appearance="light"
                  size="sm"
                >
                  <BadgeDot />
                  {row.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </span>
            </div>
          </div>

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
