'use client';

import { useState } from 'react';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import type {
  IndexMatch,
  IndexMatchOutcome,
  IndexMatchRow,
} from '../types/chatbotTurn.types';

const OUTCOME_VARIANT: Record<IndexMatchOutcome, BadgeProps['variant']> = {
  kept: 'success',
  dropped: 'destructive',
  changed: 'warning',
};

const LABELS = [
  'Word',
  'Matched list entry',
  'What the bot understood',
  'Kept or dropped',
] as const;

const FLOW = 'grid gap-2 sm:grid-cols-4 sm:gap-3';

function Cell({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1">
      <div className="text-2xs font-medium text-muted-foreground sm:hidden">
        {label}
      </div>
      {children}
    </div>
  );
}

const OUTCOME_WORD: Record<IndexMatchOutcome, string> = {
  kept: 'Kept',
  dropped: 'Dropped',
  changed: 'Changed',
};

/** The outcome word in the badge; the reason, when there is one, as plain muted text beside it. */
function Outcome({
  outcome,
  text,
}: {
  outcome: IndexMatchOutcome;
  text: string;
}) {
  const word = OUTCOME_WORD[outcome];
  const reason = text.startsWith(`${word}: `)
    ? text.slice(word.length + 2)
    : '';
  return (
    <div
      className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5"
      data-testid="index-outcome"
    >
      <Badge variant={OUTCOME_VARIANT[outcome]} appearance="light" size="sm">
        {reason ? word : text}
      </Badge>
      {reason && (
        <span className="min-w-0 break-words text-muted-foreground">
          <span className="sr-only">: </span>
          {reason}
        </span>
      )}
    </div>
  );
}

function FlowRow({
  testId,
  word,
  row,
  showDetails,
}: {
  testId?: string;
  word: React.ReactNode;
  row: Omit<IndexMatchRow, 'word'>;
  showDetails: boolean;
}) {
  const pairs = Math.max(row.understood.length, row.result.length);
  return (
    <div
      data-testid={testId}
      className={`${FLOW} rounded-md border p-2 text-xs`}
    >
      <Cell label={LABELS[0]}>{word}</Cell>
      <Cell label={LABELS[1]}>
        {row.matched.map((m, i) => (
          <div key={i} className="break-words">
            {m.plain}
            <div className="text-2xs text-muted-foreground">
              {m.source}
              {m.close_spelling && (
                <Badge
                  variant="secondary"
                  appearance="light"
                  size="sm"
                  className="ms-1"
                >
                  close spelling
                </Badge>
              )}
            </div>
          </div>
        ))}
      </Cell>
      <div className="min-w-0 space-y-2 sm:col-span-2">
        {pairs === 0 && (
          <div className="grid gap-2 sm:grid-cols-2 sm:gap-3">
            <Cell label={LABELS[2]}>
              <span className="text-muted-foreground">-</span>
            </Cell>
            <Cell label={LABELS[3]}>
              <span className="text-muted-foreground">-</span>
            </Cell>
          </div>
        )}
        {Array.from({ length: pairs }, (_, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-2 sm:gap-3">
            <Cell label={LABELS[2]}>
              <div className="break-words">{row.understood[i]?.text}</div>
            </Cell>
            <Cell label={LABELS[3]}>
              {row.result[i] && (
                <Outcome
                  outcome={row.result[i].outcome}
                  text={row.result[i].text}
                />
              )}
            </Cell>
          </div>
        ))}
      </div>
      {showDetails && row.parser_got.length > 0 && (
        <div className="min-w-0 space-y-1 sm:col-span-4">
          <div className="text-2xs font-medium text-muted-foreground">
            What the bot was given
          </div>
          {row.parser_got.map((line, i) => (
            <div key={i} className="break-words font-mono text-2xs">
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function IndexMatchSection({
  indexMatch,
}: {
  indexMatch: IndexMatch | null;
}) {
  const [showDetails, setShowDetails] = useState(false);
  if (!indexMatch) {
    return (
      <p className="text-xs text-muted-foreground">
        No list matching was recorded on this turn.
      </p>
    );
  }
  if (indexMatch.failed) {
    return (
      <p className="text-xs text-muted-foreground">
        The matching step failed on this turn; the bot ran without it.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">
        {indexMatch.words.map((w, i) =>
          w.matched ? (
            <Badge key={i} variant="primary" size="sm">
              {w.text}
            </Badge>
          ) : (
            <span
              key={i}
              className="rounded border px-1.5 py-0.5 text-xs text-muted-foreground"
            >
              {w.text}
            </span>
          ),
        )}
      </div>
      {indexMatch.rows.length === 0 &&
      indexMatch.not_from_lists.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No word of this message matched a list entry.
        </p>
      ) : (
        <div className="space-y-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-expanded={showDetails}
            onClick={() => setShowDetails((v) => !v)}
          >
            {showDetails ? 'Hide details' : 'Show details'}
          </Button>
          <div
            className={`${FLOW} hidden px-2 text-2xs font-medium text-muted-foreground sm:grid`}
          >
            {LABELS.map((label) => (
              <div key={label}>{label}</div>
            ))}
          </div>
          {indexMatch.rows.map((row) => (
            <FlowRow
              key={row.word}
              testId={`index-row-${row.word}`}
              word={<span className="font-medium">{row.word}</span>}
              row={row}
              showDetails={showDetails}
            />
          ))}
          {indexMatch.not_from_lists.map((n, i) => (
            <FlowRow
              key={`n${i}`}
              word={
                <span className="text-muted-foreground">
                  (not from the lists)
                </span>
              }
              row={{
                matched: [],
                parser_got: [],
                understood: [{ text: n.text }],
                result: [{ outcome: n.outcome, text: n.result }],
              }}
              showDetails={showDetails}
            />
          ))}
        </div>
      )}
      {indexMatch.looked_up && (
        <div className="space-y-1 text-xs" data-testid="index-looked-up">
          <div className="text-2xs font-medium text-muted-foreground">
            What the bot looked up
          </div>
          <div className="font-medium">{indexMatch.looked_up.what}</div>
          {indexMatch.looked_up.details.length > 0 && (
            <ul className="space-y-0.5 text-muted-foreground">
              {indexMatch.looked_up.details.map((d, i) => (
                <li key={i} className="break-words">
                  {d}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {indexMatch.held.length > 0 && (
        <Collapsible defaultOpen={false}>
          <CollapsibleTrigger className="text-xs font-medium text-muted-foreground">
            Also sent: {indexMatch.held.length}{' '}
            {indexMatch.held.length === 1 ? 'line' : 'lines'} on record for the
            held product
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-1 space-y-1 text-2xs">
              {indexMatch.held.map((line, i) => (
                <li key={i} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
