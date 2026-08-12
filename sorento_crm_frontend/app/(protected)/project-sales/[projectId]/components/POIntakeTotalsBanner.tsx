'use client';

import * as React from 'react';
import { AlertTriangle, CheckCircle2, CircleHelp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { POVersion } from '../../_shared/types/poIntake.types';
import { formatMyrExact, isMoneyZero, subtractMoney, sumMoney } from '../../_shared/lib/money';

/**
 * The first thing on the confirm screen, in money.
 *
 * When our sum of the lines differs from the total printed on the paper, that difference is
 * the best available signal that a page was misread, and it is the one thing a person can
 * act on before reading anything else. It is therefore stated at the top, as an amount, not
 * as a per-line flag somewhere down the table.
 *
 * One case is deliberately NOT alarming: once a handwritten cancellation has been accepted,
 * our sum legitimately drops below the printed total by exactly the cancelled amount. That
 * difference is explained, so it reads as a fact rather than a fault. Everything else is a
 * fault until a person says otherwise.
 */
export function POIntakeTotalsBanner({
  version,
  onJumpToProblem,
}: {
  version: POVersion;
  onJumpToProblem?: () => void;
}) {
  const { totals, lines } = version;
  const cancelled = lines.filter((line) => line.is_cancelled);
  const cancelledTotal = sumMoney(cancelled.map((line) => line.amount));
  const difference = subtractMoney(totals.lines_total, totals.extracted_total);
  const arithmeticFailures = Math.max(
    0,
    totals.arithmetic_total - totals.arithmetic_passed,
  );

  // difference == -cancelledTotal, i.e. difference + cancelledTotal == 0, means the gap IS
  // the cancellations and nothing else.
  const explainedByCancellations =
    difference !== null &&
    cancelledTotal !== null &&
    !isMoneyZero(cancelledTotal) &&
    isMoneyZero(sumMoney([difference, cancelledTotal]));

  if (totals.extracted_total === null) {
    return (
      <Banner
        tone="unknown"
        icon={<CircleHelp className="size-4 shrink-0" aria-hidden />}
        headline="The document's own total could not be read"
        detail={`Our sum of the lines is ${formatMyrExact(totals.lines_total)}. Check it against the paper before you confirm.`}
        arithmeticFailures={arithmeticFailures}
        onJumpToProblem={onJumpToProblem}
      />
    );
  }

  if (difference === null) {
    return (
      <Banner
        tone="unknown"
        icon={<CircleHelp className="size-4 shrink-0" aria-hidden />}
        headline="The two totals could not be compared"
        detail={`Document total ${formatMyrExact(totals.extracted_total)}, our sum ${formatMyrExact(totals.lines_total)}.`}
        arithmeticFailures={arithmeticFailures}
        onJumpToProblem={onJumpToProblem}
      />
    );
  }

  if (isMoneyZero(difference)) {
    return (
      <Banner
        tone="match"
        icon={<CheckCircle2 className="size-4 shrink-0" aria-hidden />}
        headline={`Our sum of the lines matches the document total, ${formatMyrExact(totals.extracted_total)}`}
        detail={`${totals.arithmetic_passed} of ${totals.arithmetic_total} lines multiply out.`}
        arithmeticFailures={arithmeticFailures}
        onJumpToProblem={onJumpToProblem}
      />
    );
  }

  const shortfall = difference.startsWith('-');
  const magnitude = formatMyrExact(difference.replace('-', ''));

  if (explainedByCancellations) {
    return (
      <Banner
        tone="explained"
        icon={<CircleHelp className="size-4 shrink-0" aria-hidden />}
        headline={`Our sum is ${magnitude} below the document total, which is the ${cancelled.length} cancelled line${cancelled.length === 1 ? '' : 's'}`}
        detail={`Document total ${formatMyrExact(totals.extracted_total)}, our sum of the live lines ${formatMyrExact(totals.lines_total)}.`}
        arithmeticFailures={arithmeticFailures}
        onJumpToProblem={onJumpToProblem}
      />
    );
  }

  return (
    <Banner
      tone="mismatch"
      icon={<AlertTriangle className="size-4 shrink-0" aria-hidden />}
      headline={`Our sum of the lines is ${magnitude} ${shortfall ? 'below' : 'above'} the total printed on the document`}
      detail={`Document total ${formatMyrExact(totals.extracted_total)}, our sum ${formatMyrExact(totals.lines_total)}.`}
      arithmeticFailures={arithmeticFailures}
      onJumpToProblem={onJumpToProblem}
    />
  );
}

const TONE_CLASS: Record<string, string> = {
  mismatch: 'border-destructive/40 bg-destructive/5 text-destructive',
  explained:
    'border-amber-500/40 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-300',
  unknown:
    'border-amber-500/40 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-300',
  match:
    'border-emerald-500/40 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300',
};

function Banner({
  tone,
  icon,
  headline,
  detail,
  arithmeticFailures,
  onJumpToProblem,
}: {
  tone: keyof typeof TONE_CLASS;
  icon: React.ReactNode;
  headline: string;
  detail: string;
  arithmeticFailures: number;
  onJumpToProblem?: () => void;
}) {
  return (
    <div
      role="status"
      data-tone={tone}
      className={`flex flex-col gap-2 rounded-lg border px-4 py-3 sm:flex-row sm:items-start sm:justify-between ${TONE_CLASS[tone]}`}
    >
      <div className="flex min-w-0 gap-2">
        {icon}
        <div className="min-w-0 break-words">
          <p className="text-sm font-semibold">{headline}</p>
          <p className="mt-0.5 text-xs opacity-90">{detail}</p>
          {arithmeticFailures > 0 && (
            <p className="mt-0.5 text-xs font-medium">
              {arithmeticFailures === 1
                ? '1 line does not multiply out.'
                : `${arithmeticFailures} lines do not multiply out.`}
            </p>
          )}
        </div>
      </div>
      {onJumpToProblem && (tone === 'mismatch' || arithmeticFailures > 0) && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={onJumpToProblem}
        >
          Go to the first problem line
        </Button>
      )}
    </div>
  );
}
