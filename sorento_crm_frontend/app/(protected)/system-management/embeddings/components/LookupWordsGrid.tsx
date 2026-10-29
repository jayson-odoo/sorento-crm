'use client';

import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';

import type { LookupWord, LookupWordRow, WordHome } from '../types/embeddings.types';
import { HOME_LABEL, HOME_ORDER } from '../lib';

function Dot({ filled }: { filled: boolean }) {
  return (
    <i
      data-testid="vector-dot"
      data-filled={filled ? 'true' : 'false'}
      title={filled ? 'Vector stored' : 'No vector yet'}
      className={`inline-block size-2 shrink-0 rounded-full border ${filled ? 'border-primary bg-primary' : 'border-muted-foreground bg-transparent'}`}
    />
  );
}

function WordGroups({ words }: { words: LookupWord[] }) {
  const groups = HOME_ORDER.map((home) => ({ home, items: words.filter((w) => w.home === home) })).filter((g) => g.items.length);
  const other = words.filter((w) => !w.home || !HOME_ORDER.includes(w.home as WordHome));
  return (
    <div className="space-y-1 py-1">
      {groups.map((g) => (
        <div key={g.home} className="flex flex-wrap items-center gap-1.5">
          <span className="w-24 shrink-0 text-xs text-muted-foreground">{HOME_LABEL[g.home]}</span>
          {g.items.map((w) => (
            <span key={w.text} className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs">
              <Dot filled={w.has_vector} />
              {w.text}
            </span>
          ))}
        </div>
      ))}
      {other.length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {other.map((w) => (
            <span key={w.text} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs">
              <Dot filled={w.has_vector} />
              {w.text}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function LookupWordsGrid({
  rows,
  isLoading,
  error,
  onRetry,
}: {
  rows: LookupWordRow[];
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const columns = useMemo<ColumnDef<LookupWordRow>[]>(
    () => [
      {
        id: 'row',
        header: 'Row',
        size: 200,
        meta: { headerTitle: 'Row' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.label}>
            {row.original.label}
          </span>
        ),
      },
      {
        id: 'source',
        header: 'Source',
        size: 160,
        meta: { headerTitle: 'Source' },
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground" title={row.original.source}>
            {row.original.source}
          </span>
        ),
      },
      {
        id: 'words',
        header: 'Words matched on',
        size: 560,
        meta: { headerTitle: 'Words matched on' },
        cell: ({ row }) => <WordGroups words={row.original.words} />,
      },
      {
        id: 'vectors',
        header: 'Vectors',
        size: 100,
        meta: { headerTitle: 'Vectors' },
        cell: ({ row }) => {
          const have = row.original.words.filter((w) => w.has_vector).length;
          const all = row.original.words.length;
          return (
            <Badge variant={have === all ? 'success' : 'warning'} appearance="light" size="sm">
              {have} / {all}
            </Badge>
          );
        },
      },
    ],
    [],
  );

  return (
    <PanelDataGrid<LookupWordRow>
      listingKey={null}
      columns={columns}
      rows={rows}
      getRowId={(r) => r.key}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle="No rows"
      searchPlaceholder="Search rows or words..."
      searchOf={(r) => `${r.label} ${r.words.map((w) => w.text).join(' ')}`}
      pageSize={25}
    />
  );
}
