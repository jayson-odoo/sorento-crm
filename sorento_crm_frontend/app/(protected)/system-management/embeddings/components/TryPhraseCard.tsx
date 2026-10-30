'use client';

import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';

import type { TryCandidate, TryCell, TryResult } from '../types/embeddings.types';
import { HOME_LABEL } from '../lib';
import { score } from '../lib';

function Signal({ cell, floor, extra }: { cell: TryCell | null; floor: number; extra?: React.ReactNode }) {
  if (!cell) return <span className="text-muted-foreground">-</span>;
  const reached = cell.score >= floor;
  return (
    <div className="min-w-0 space-y-0.5">
      <div className="flex items-baseline gap-1">
        <span className={reached ? 'font-semibold text-green-600' : ''}>{score(cell.score)}</span>
        <span className="text-xs text-muted-foreground">/</span>
        <span className="text-xs text-muted-foreground">{score(floor)}</span>
      </div>
      {cell.text ? (
        <div className="truncate text-xs text-muted-foreground" title={cell.text}>
          <span>{cell.text}</span>
          {cell.home ? <span> ({HOME_LABEL[cell.home].toLowerCase()})</span> : null}
        </div>
      ) : null}
      {extra}
    </div>
  );
}

export function TryPhraseCard({
  result,
  pending,
  onTry,
}: {
  result: TryResult | undefined;
  pending: boolean;
  onTry: (phrase: string) => void;
}) {
  const [phrase, setPhrase] = useState('');

  const columns = useMemo<ColumnDef<TryCandidate>[]>(
    () => [
      {
        id: 'row',
        header: 'Row',
        size: 220,
        meta: { headerTitle: 'Row' },
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="truncate font-medium" title={row.original.label}>{row.original.label}</div>
            <div className="text-xs text-muted-foreground">{row.original.list.replace(/_/g, ' ')}</div>
          </div>
        ),
      },
      {
        id: 'spelling',
        header: 'Spelling',
        size: 200,
        meta: { headerTitle: 'Spelling' },
        cell: ({ row }) => <Signal cell={row.original.spelling} floor={row.original.floors.spell} />,
      },
      {
        id: 'vector',
        header: 'Vector',
        size: 200,
        meta: { headerTitle: 'Vector' },
        cell: ({ row }) => <Signal cell={row.original.vector} floor={row.original.floors.meaning} />,
      },
      {
        id: 'partial',
        header: 'Partial',
        size: 110,
        meta: { headerTitle: 'Partial' },
        cell: ({ row }) => (
          <div className="flex items-baseline gap-1">
            <span>{score(row.original.partial)}</span>
            <span className="text-xs text-muted-foreground">/</span>
            <span className="text-xs text-muted-foreground">{score(row.original.floors.partial)}</span>
          </div>
        ),
      },
      {
        id: 'result',
        header: 'Result',
        size: 130,
        meta: { headerTitle: 'Result' },
        cell: ({ row }) => (
          <Badge variant={row.original.passed ? 'success' : 'secondary'} appearance="light" size="sm">
            {row.original.passed ? 'Pass' : 'Fail'}
          </Badge>
        ),
      },
    ],
    [],
  );

  const submit = () => {
    const text = phrase.trim();
    if (text) onTry(text);
  };

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Try a phrase</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Input
            aria-label="Phrase"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder="Type a phrase"
            className="min-w-0 flex-1 sm:max-w-md"
          />
          <Button type="submit" variant="outline" disabled={pending || !phrase.trim()}>
            Try
          </Button>
          {result ? (
            <Badge
              variant={result.verdict === 'resolved' ? 'success' : result.verdict === 'ambiguous' ? 'warning' : 'secondary'}
              appearance="light"
            >
              {result.verdict.charAt(0).toUpperCase() + result.verdict.slice(1)}
            </Badge>
          ) : null}
        </form>
        {result ? (
          <PanelDataGrid<TryCandidate>
            listingKey={null}
            columns={columns}
            rows={result.candidates}
            getRowId={(c) => `${c.list}:${c.key}`}
            emptyTitle="No rows came near"
            paginate={false}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}
