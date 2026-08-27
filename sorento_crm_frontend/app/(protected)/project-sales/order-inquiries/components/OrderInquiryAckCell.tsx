'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { BoardChangeTable } from '../../fulfilment-planning/components/BoardChangeTable';
import {
  ACK_LABELS,
  ACK_VARIANTS,
  ackStateOf,
  previousValueOf,
} from '../../_shared/lib/orderInquiryAck';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

/**
 * The Confirmed column (AC-D15): one badge and the fact behind it.
 *
 * Four readings, and each says a different thing to a buyer scanning the column:
 * nobody has said yes to this yet; Joey confirmed it at that time; CS moved it after she
 * did, and here is what it was; purchasing refused it, and here is why. The refusal
 * prints its reason inline because a refusal nobody can read is the thing this exists to
 * stop. The words come from `ACK_LABELS`, which is where Acknowledge became Confirm (R7).
 *
 * A CHANGED row draws the same Was / Now table the board draws for a planning change
 * (part 3), so the two screens say a change the same way. Its Decision row is omitted
 * here: an order inquiry row carries a quantity and a date, and no decision of its own.
 */
export function OrderInquiryAckCell({ row }: { row: OrderInquiryWorklistRow }) {
  const state = ackStateOf(row);
  const previous = state === 'changed' ? previousValueOf(row) : null;

  if (state === 'rejected') {
    const reason = (row.rejected_reason ?? '').trim();
    const line = reason
      ? `Rejected: ${reason}`
      : `Rejected${row.rejected_by_name ? ` by ${row.rejected_by_name}` : ''}`;
    return (
      <div className="min-w-0">
        <Badge variant="destructive" appearance="light" size="sm">
          {ACK_LABELS.rejected}
        </Badge>
        <span className="block truncate text-2xs text-muted-foreground" title={line}>
          {reason && row.rejected_by_name ? `${row.rejected_by_name}: ${reason}` : line}
        </span>
      </div>
    );
  }

  if (state === 'changed') {
    return (
      <div className="min-w-0 space-y-1">
        <Badge variant="warning" appearance="light" size="sm">
          {row.changed_at
            ? `${ACK_LABELS.changed} ${formatDateInMalaysia(row.changed_at)}`
            : ACK_LABELS.changed}
        </Badge>
        {previous ? (
          <BoardChangeTable
            compact
            omitDecision
            annotation={{
              rowId: row.id,
              soNumber: row.so_number ?? '',
              lineNo: 0,
              itemCode: row.item_code ?? '',
              // The batch's own change vocabulary is never shown (part 3) and this
              // table prints none of it; `qty_up` is the nearest true word for a row CS
              // amended, and nothing reads it here.
              kind: 'qty_up',
              closed: false,
              was: { qty: previous.qty, date: previous.date, decision: null },
              now: { qty: row.qty, date: row.delivery_date ?? null, decision: null },
              movedTransfer: null,
              projectLineId: null,
            }}
          />
        ) : null}
      </div>
    );
  }

  if (state === 'acknowledged') {
    const who = row.acknowledged_by_name ?? 'Purchasing';
    const when = row.acknowledged_at ? formatDateTimeInMalaysia(row.acknowledged_at) : '';
    const title = when ? `${who} ${when}` : who;
    return (
      <div className="min-w-0">
        <Badge variant={ACK_VARIANTS.acknowledged} appearance="light" size="sm">
          {ACK_LABELS.acknowledged}
        </Badge>
        <span className="block truncate text-2xs text-muted-foreground" title={title}>
          {title}
        </span>
      </div>
    );
  }

  return (
    <Badge variant={ACK_VARIANTS.awaiting} appearance="light" size="sm">
      {ACK_LABELS.awaiting}
    </Badge>
  );
}

export default OrderInquiryAckCell;
