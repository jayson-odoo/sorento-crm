'use client';

import type { ReactNode } from 'react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { formatDate, timeAgo } from '@/lib/helpers';
import { specTypeLabel } from '../../lib/specTypeLabel';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function HeaderField({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="min-w-0" data-testid={`spec-header-${id}`}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm">{children}</dd>
    </div>
  );
}

/**
 * The record header card, the same shape as every other record header (Users &
 * Access; fix round 5, owner ruling 27 Sep 2026: "still pretty empty"): the
 * specification's name as the title and its In use state as a pill on the left,
 * the pager, gear and primary on the right, then the type, the choices count, the
 * products count and when the catalogue was last read. Read-only in both modes;
 * the one place the identity fields are editable is Details. Still no code name,
 * no "Built in" and no rule count (AC-S3.7).
 */
export function SpecKeyRecordCard({
  row,
  productsCount,
  lastReadAt,
  classChoiceCount,
  mode,
  pagerNode,
  actions,
  pending,
  primary,
}: {
  row: SpecRegistryKey;
  /** How many products carry this specification now. `undefined` while it loads. */
  productsCount?: number | null;
  /** When a product carrying it was last read. `null` when none has been. */
  lastReadAt?: string | null;
  /** Product class is open-vocabulary: its choices are the category master's class
   *  labels, not its (empty) `allowed_values` - the same count the list shows. */
  classChoiceCount?: number;
  mode: 'view' | 'edit';
  pagerNode: ReactNode;
  actions: RecordAction[];
  pending: ReactNode;
  primary: ReactNode;
}) {
  const hasChoices = row.data_type !== 'numeric' && row.data_type !== 'boolean';
  const choices =
    row.spec_key === 'class' ? classChoiceCount ?? 0 : row.allowed_values.length;

  return (
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 py-4 lg:flex-row lg:items-center lg:justify-between">
        <CardHeading className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="break-words">{row.label}</CardTitle>
            <Badge
              data-testid="spec-header-state"
              variant={row.is_active ? 'success' : 'secondary'}
              appearance="light"
              size="sm"
              shape="circle"
            >
              <BadgeDot />
              {row.is_active ? 'In use' : 'Not in use'}
            </Badge>
          </div>
        </CardHeading>
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
      </CardHeader>
      <CardContent className="py-4">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <HeaderField id="type" label="Type">
            <span>{specTypeLabel(row.data_type, row.unit)}</span>
          </HeaderField>
          <HeaderField id="choices" label="Choices">
            {hasChoices ? (
              <span className="tabular-nums">{choices.toLocaleString()}</span>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </HeaderField>
          <HeaderField id="products" label="Products">
            {productsCount == null ? (
              <span className="text-muted-foreground">-</span>
            ) : (
              <span className="tabular-nums">{productsCount.toLocaleString()}</span>
            )}
          </HeaderField>
          <HeaderField id="last-read" label="Last read">
            {lastReadAt === undefined ? (
              <span className="text-muted-foreground">-</span>
            ) : lastReadAt === null ? (
              <span className="text-muted-foreground">Not read yet</span>
            ) : (
              <span title={timeAgo(lastReadAt)}>{formatDate(lastReadAt)}</span>
            )}
          </HeaderField>
        </dl>
      </CardContent>
    </Card>
  );
}

export default SpecKeyRecordCard;
