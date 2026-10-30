'use client';

import * as React from 'react';
import { Flag, Loader2 } from 'lucide-react';
import { parseDateTimeAsUTC } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import {
  AT_RISK_MS,
  chipClass,
} from '@/app/(protected)/sla-management/conversation-sla-tracking/components/TicketSlaChips';
import { useEscalateMedia } from '../../_shared/hooks/useProjects';
import type {
  MediaKind,
  QuotationLine,
} from '../../_shared/types/project.types';

const TZ = 'Asia/Kuala_Lumpur';

function when(value: string, withYear: boolean): string {
  const date = parseDateTimeAsUTC(value);
  const day = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: TZ,
  });
  if (!withYear) return day.format(date);
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: 'numeric',
    minute: '2-digit',
    hourCycle: 'h12',
    timeZone: TZ,
  });
  const year = new Intl.DateTimeFormat('en-GB', {
    year: 'numeric',
    timeZone: TZ,
  });
  return `${day.format(date)} ${year.format(date)}, ${time.format(date).toUpperCase()}`;
}

function whenShort(value: string): string {
  const date = parseDateTimeAsUTC(value);
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: 'numeric',
    minute: '2-digit',
    hourCycle: 'h12',
    timeZone: TZ,
  });
  return `${when(value, false)}, ${time.format(date).toUpperCase()}`;
}

/**
 * The Drawing or Photo cell of a saved catalogue line whose product has none: Escalate, or the state
 * of the request already open for that product. The tile styling follows the "Choose" picker
 * trigger beside it; the colour of an open request follows the SLA chips' deadline rule.
 */
export function MediaEscalation({
  kind,
  line,
  code,
}: {
  kind: MediaKind;
  line: QuotationLine;
  code: string | null;
}) {
  const escalate = useEscalateMedia(line.version_id, kind);
  const state =
    (kind === 'photo' ? line.product_image : line.technical_drawing)
      ?.escalation ?? null;
  const open = state?.tracking_id && state.opened_at ? state : null;
  const driver =
    line.set_parts?.find((part) => part.is_driver)?.product_code ?? null;

  if (open) {
    const responded = Boolean(open.responded_at);
    const msLeft = open.due_at
      ? parseDateTimeAsUTC(open.due_at).getTime() - Date.now()
      : null;
    // Responded reads blue while there is time; amber and red override it, as on the SLA chips.
    const tone =
      msLeft != null && msLeft < AT_RISK_MS
        ? chipClass(msLeft)
        : responded
          ? 'border-primary text-primary'
          : chipClass(msLeft);
    const people = open.requester_count ?? 0;
    const hover = responded
      ? `Responded ${whenShort(open.responded_at as string)}` +
        (open.due_at ? `. Due ${whenShort(open.due_at)}.` : '.')
      : `Escalated ${when(open.opened_at as string, true)} by ${people} ${people === 1 ? 'person' : 'people'}` +
        (open.due_at ? `. Due ${whenShort(open.due_at)}.` : '.');
    // The tile joins the open request (the server records each person once), so a later
    // salesperson on any quotation with this product is added as a requester.
    const joinLabel = `Join the ${kind} request for ${driver ?? code ?? 'this product'}`;
    return (
      <button
        type="button"
        title={hover}
        aria-label={joinLabel}
        aria-busy={escalate.isPending}
        disabled={escalate.isPending}
        onClick={() => escalate.mutate(line.id)}
        className={cn(
          'flex aspect-square max-h-48 w-full flex-col items-center justify-center gap-0.5 overflow-hidden rounded border px-0 py-0.5 text-center text-2xs leading-tight tracking-tighter',
          tone,
          escalate.isPending && 'cursor-progress opacity-60',
        )}
      >
        <Flag className="size-3.5" aria-hidden="true" />
        {responded ? 'Replied' : 'Escalated'}
        <br />
        {when(
          (responded ? open.responded_at : open.opened_at) as string,
          false,
        )}
      </button>
    );
  }

  const lastResolved = state?.last_resolved_at ?? null;
  const name = driver ?? code ?? 'this product';
  const ask = `Ask for a ${kind} of ${name}`;
  return (
    <button
      type="button"
      aria-label={`Escalate missing ${kind} for ${name}`}
      aria-busy={escalate.isPending}
      disabled={escalate.isPending}
      title={
        lastResolved
          ? `Last request resolved ${when(lastResolved, false)}, no ${kind} on file. ${ask}`
          : ask
      }
      onClick={() => escalate.mutate(line.id)}
      className={cn(
        'flex aspect-square max-h-48 w-full flex-col items-center justify-center gap-0.5 rounded border border-dashed border-primary bg-primary/5 p-0.5 text-center text-2xs leading-tight text-primary',
        escalate.isPending && 'cursor-progress opacity-60',
      )}
    >
      {escalate.isPending ? (
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <Flag className="size-3.5" aria-hidden="true" />
      )}
      Escalate
    </button>
  );
}
