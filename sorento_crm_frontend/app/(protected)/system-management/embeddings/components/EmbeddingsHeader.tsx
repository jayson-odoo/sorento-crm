'use client';

import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { Skeleton } from '@/components/ui/skeleton';

import type { EmbeddingsOverview } from '../types/embeddings.types';
import { num } from '../lib';

export type EmbeddingsMode = 'lookup' | 'records';

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <div className="text-xs text-muted-foreground truncate">{label}</div>
      <div className="text-sm font-medium truncate flex items-center gap-2">{children}</div>
    </div>
  );
}

/** Page header with its one call to action, and the strip of what is embedded with what. */
export function EmbeddingsHeader({
  overview,
  loading,
  mode,
  onEmbedMissing,
  embedPending,
  onStartBackfill,
  backfillPending,
}: {
  overview: EmbeddingsOverview | undefined;
  loading: boolean;
  mode: EmbeddingsMode;
  onEmbedMissing: () => void;
  embedPending: boolean;
  onStartBackfill: () => void;
  backfillPending: boolean;
}) {
  const cta =
    mode === 'lookup' ? (
      <Button onClick={onEmbedMissing} disabled={embedPending}>
        {embedPending ? <Loader2 className="size-4 animate-spin" /> : null}
        Embed missing
      </Button>
    ) : (
      <Button onClick={onStartBackfill} disabled={backfillPending}>
        {backfillPending ? <Loader2 className="size-4 animate-spin" /> : null}
        Start backfill
      </Button>
    );

  const model = overview?.setting.model;
  const searchModel = overview?.records_search_model;
  const onTarget = overview?.records.reduce((sum, r) => sum + (model ? (r.chunks_by_model[model] ?? 0) : 0), 0) ?? 0;
  const onSearch = overview?.records.reduce((sum, r) => sum + (searchModel ? (r.chunks_by_model[searchModel] ?? 0) : 0), 0) ?? 0;

  return (
    <>
      <Container>
        <PageHeader title="Embeddings" actions={cta} />
      </Container>
      <Container>
        {loading || !overview ? (
          <Skeleton className="h-14 w-full" />
        ) : (
          <div className="grid grid-cols-2 gap-4 rounded-lg border border-border p-4 lg:grid-cols-4">
            <Metric label="Embedder">{overview.setting.model}</Metric>
            <Metric label="Lookup words with a vector">
              {num(overview.lookup.texts_with_vector)} / {num(overview.lookup.texts_total)}
            </Metric>
            {mode === 'lookup' ? (
              <Metric label={`Record chunks on ${overview.setting.model}`}>
                {num(onTarget)} / {num(onSearch)}
              </Metric>
            ) : (
              <Metric label="Records left to embed">{num(overview.guard.remaining)}</Metric>
            )}
            <Metric label="Record search reads">
              {overview.records_search_model}
              {overview.records_search_model !== overview.setting.model ? (
                <Badge variant="warning" size="sm">
                  {overview.guard.ready ? 'Ready to switch' : `${overview.setting.model} in progress`}
                </Badge>
              ) : null}
            </Metric>
          </div>
        )}
      </Container>
    </>
  );
}
