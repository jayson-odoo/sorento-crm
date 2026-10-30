'use client';

import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';

import type { EmbeddingsOverview } from '../types/embeddings.types';
import { num, sourceName } from '../lib';

type Record_ = EmbeddingsOverview['records'][number];

export function RecordsGrid({ overview }: { overview: EmbeddingsOverview }) {
  const target = overview.setting.model;
  const search = overview.records_search_model;

  const columns = useMemo<ColumnDef<Record_>[]>(
    () => [
      {
        id: 'source',
        header: 'Source',
        size: 200,
        meta: { headerTitle: 'Source' },
        cell: ({ row }) => <span className="block truncate font-medium" title={sourceName(row.original.source_type)}>{sourceName(row.original.source_type)}</span>,
      },
      {
        id: 'documents',
        header: 'Documents',
        size: 130,
        meta: { headerTitle: 'Documents' },
        cell: ({ row }) => <span className="tabular-nums">{num(row.original.documents)}</span>,
      },
      {
        id: 'search',
        header: search,
        size: 220,
        meta: { headerTitle: search },
        cell: ({ row }) => <span className="tabular-nums">{num(row.original.chunks_by_model[search] ?? 0)}</span>,
      },
      ...(target !== search
        ? [
            {
              id: 'target',
              header: target,
              size: 220,
              meta: { headerTitle: target },
              cell: ({ row }: { row: { original: Record_ } }) => (
                <span className="tabular-nums">{num(row.original.chunks_by_model[target] ?? 0)}</span>
              ),
            } satisfies ColumnDef<Record_>,
          ]
        : []),
      {
        id: 'coverage',
        header: 'Coverage',
        size: 120,
        meta: { headerTitle: 'Coverage' },
        cell: ({ row }) => {
          const have = row.original.chunks_by_model[target] ?? 0;
          const all = row.original.chunks_by_model[search] ?? 0;
          const pct = all > 0 ? Math.min(100, Math.round((have / all) * 100)) : have > 0 ? 100 : 0;
          return (
            <Badge variant={pct >= 100 ? 'success' : 'warning'} appearance="light" size="sm">
              {pct}%
            </Badge>
          );
        },
      },
    ],
    [target, search],
  );

  return (
    <PanelDataGrid<Record_>
      listingKey={null}
      columns={columns}
      rows={overview.records}
      getRowId={(r) => r.source_type}
      emptyTitle="No records"
      paginate={false}
    />
  );
}
