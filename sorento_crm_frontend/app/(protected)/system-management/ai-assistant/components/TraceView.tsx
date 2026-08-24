'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import { useQueryTrace } from '../hooks/useAIUsage';
import type { SpanKind, Trace, TraceSpan } from '../services/aiUsageService';

const KIND_VARIANT: Record<string, 'primary' | 'success' | 'info' | 'warning' | 'destructive' | 'secondary'> = {
  AGENT: 'secondary',
  LLM: 'primary',
  TOOL: 'info',
  RETRIEVER: 'success',
  CHAIN: 'secondary',
  GUARDRAIL: 'warning',
  EMBEDDING: 'success',
  EVALUATOR: 'warning',
};

const ALL_KINDS: SpanKind[] = [
  'AGENT',
  'LLM',
  'TOOL',
  'RETRIEVER',
  'CHAIN',
  'GUARDRAIL',
  'EMBEDDING',
  'EVALUATOR',
];

function depthOf(span: TraceSpan, byId: Map<string, TraceSpan>): number {
  let d = 0;
  let cur: TraceSpan | undefined = span;
  const seen = new Set<string>();
  while (cur && cur.parent_id && !seen.has(cur.id)) {
    seen.add(cur.id);
    cur = byId.get(cur.parent_id);
    d += 1;
    if (d > 32) break;
  }
  return d;
}

function pretty(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function isTruncated(
  value: unknown,
): value is { truncated: true; byte_size: number; preview: string } {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { truncated?: unknown }).truncated === true &&
    typeof (value as { preview?: unknown }).preview === 'string'
  );
}

function JsonPanel({ title, value }: { title: string; value: unknown }) {
  const truncated = isTruncated(value);
  // A truncated payload is the {truncated,byte_size,preview} envelope the
  // backend substitutes past the byte cap - show the preview + a banner, not
  // the raw envelope blob.
  const text = truncated ? value.preview : pretty(value);
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      {truncated ? (
        <div className="mb-1 rounded-md border border-warning/40 bg-warning/5 px-2 py-1 text-[11px] text-muted-foreground">
          Truncated - showing first {(value.preview.length / 1000).toFixed(1)} KB of{' '}
          {(value.byte_size / 1000).toFixed(1)} KB.
        </div>
      ) : null}
      {text ? (
        <SearchableCode text={text} ariaLabel={`${title} (press Cmd/Ctrl+F to search)`} />
      ) : (
        <div className="rounded-md border p-3 text-xs italic text-muted-foreground">Empty</div>
      )}
    </div>
  );
}

function SpanInspector({ span }: { span: TraceSpan }) {
  const isLLM = span.span_kind === 'LLM';
  const isTool = span.span_kind === 'TOOL' || span.span_kind === 'GUARDRAIL';
  const isRetriever = span.span_kind === 'RETRIEVER';

  return (
    <div className="space-y-3" data-testid="trace-inspector">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={KIND_VARIANT[span.span_kind] ?? 'secondary'} appearance="light">
          {span.span_kind}
        </Badge>
        <span className="text-sm font-medium">{span.name}</span>
        {span.status === 'error' ? (
          <Badge variant="destructive" appearance="light">
            error
          </Badge>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{span.latency_ms} ms</span>
        {isLLM ? (
          <>
            <span>model: {span.request_model || '-'}</span>
            <span>
              tokens: {span.tokens_in} in / {span.tokens_out} out
            </span>
            {span.finish_reason ? <span>finish: {span.finish_reason}</span> : null}
            {span.prompt_name ? (
              <Link
                href={`/system-management/ai-assistant/prompts/${encodeURIComponent(span.prompt_name)}`}
                className="font-mono text-primary underline underline-offset-2"
                data-testid="trace-prompt-link"
              >
                {span.prompt_name}
                {span.prompt_version != null ? `@v${span.prompt_version}` : ' (fallback)'}
              </Link>
            ) : null}
          </>
        ) : null}
        {isTool && span.tool_name ? <span className="font-mono">{span.tool_name}</span> : null}
        {isRetriever && span.top_k != null ? <span>top_k: {span.top_k}</span> : null}
      </div>

      {span.error ? (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span className="break-words">{span.error}</span>
        </div>
      ) : null}

      <div className="flex flex-col gap-3 lg:flex-row">
        <JsonPanel
          title="Input"
          value={
            isTool ? span.tool_args : isRetriever ? { query: span.query, top_k: span.top_k } : span.input_json
          }
        />
        <JsonPanel
          title="Output"
          value={
            isTool ? span.tool_result : isRetriever ? span.documents : span.output_json
          }
        />
      </div>
    </div>
  );
}

function TraceWaterfall({
  trace,
  activeKinds,
  selectedId,
  onSelect,
}: {
  trace: Trace;
  activeKinds: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const byId = useMemo(() => {
    const m = new Map<string, TraceSpan>();
    trace.spans.forEach((s) => m.set(s.id, s));
    return m;
  }, [trace.spans]);

  const maxLatency = useMemo(
    () => Math.max(1, ...trace.spans.map((s) => s.latency_ms || 0)),
    [trace.spans],
  );

  const rows = trace.spans.filter((s) => activeKinds.has(s.span_kind));

  if (rows.length === 0) {
    return (
      <p className="p-4 text-sm text-muted-foreground">No spans match the selected kinds.</p>
    );
  }

  return (
    <div className="divide-y" data-testid="trace-waterfall">
      {rows.map((s) => {
        const depth = depthOf(s, byId);
        const widthPct = Math.max(4, Math.round(((s.latency_ms || 0) / maxLatency) * 100));
        const isSelected = s.id === selectedId;
        const isError = s.status === 'error';
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40',
              isSelected && 'bg-muted/60',
            )}
            data-testid="trace-span-row"
          >
            <span style={{ width: depth * 14 }} className="shrink-0" />
            <Badge
              variant={isError ? 'destructive' : KIND_VARIANT[s.span_kind] ?? 'secondary'}
              appearance="light"
              className="shrink-0"
            >
              {s.span_kind}
            </Badge>
            <span className="min-w-0 flex-1 truncate text-sm" title={s.name}>
              {s.name}
            </span>
            {s.span_kind === 'LLM' ? (
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {s.tokens_in + s.tokens_out} tok
              </span>
            ) : null}
            <div className="hidden w-40 shrink-0 sm:block">
              <div className="h-2 rounded-full bg-muted">
                <div
                  className={cn('h-2 rounded-full', isError ? 'bg-destructive' : 'bg-primary')}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            </div>
            <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
              {s.latency_ms} ms
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function TraceView({ messageId }: { messageId: string }) {
  const traceQuery = useQueryTrace(messageId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(new Set());
  const [filtersOpen, setFiltersOpen] = useState(false);

  const trace = traceQuery.data;

  const activeKinds = useMemo(() => {
    const present = new Set<string>((trace?.spans ?? []).map((s) => s.span_kind));
    return new Set([...present].filter((k) => !hiddenKinds.has(k)));
  }, [trace?.spans, hiddenKinds]);

  const selected = useMemo(
    () => trace?.spans.find((s) => s.id === selectedId) ?? trace?.spans[0] ?? null,
    [trace?.spans, selectedId],
  );

  if (traceQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Loading trace…
      </div>
    );
  }

  if (traceQuery.isError) {
    const msg = (traceQuery.error as Error)?.message || 'Failed to load trace.';
    const notFound = /no trace|404|not found/i.test(msg);
    return (
      <div className="rounded-md border p-6 text-sm" data-testid="trace-empty">
        <p className="font-medium">{notFound ? 'No trace for this turn' : 'Could not load trace'}</p>
        <p className="mt-1 text-muted-foreground">
          {notFound
            ? 'This turn ran before tracing was enabled, or its trace has been swept by retention.'
            : msg}
        </p>
      </div>
    );
  }

  if (!trace) return null;

  const presentKinds = ALL_KINDS.filter((k) => trace.spans.some((s) => s.span_kind === k));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">Trace</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={trace.status === 'error' ? 'destructive' : 'success'} appearance="light">
              {trace.status}
            </Badge>
            <span className="text-muted-foreground">{trace.span_count} spans</span>
            <span className="text-muted-foreground">{trace.latency_ms} ms</span>
            <span className="text-muted-foreground">
              {trace.total_tokens_in + trace.total_tokens_out} tokens
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setFiltersOpen((o) => !o)}
            className="gap-1"
          >
            {filtersOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            Filter kinds
          </Button>
          {filtersOpen ? (
            <div className="flex flex-wrap gap-2 pt-1">
              {presentKinds.map((k) => {
                const on = !hiddenKinds.has(k);
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() =>
                      setHiddenKinds((prev) => {
                        const next = new Set(prev);
                        if (next.has(k)) next.delete(k);
                        else next.add(k);
                        return next;
                      })
                    }
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-xs',
                      on ? 'border-primary bg-primary/10 text-primary' : 'text-muted-foreground',
                    )}
                  >
                    {k}
                  </button>
                );
              })}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm">Pipeline waterfall</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <TraceWaterfall
              trace={trace}
              activeKinds={activeKinds}
              selectedId={selected?.id ?? null}
              onSelect={setSelectedId}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Node inspector</CardTitle>
          </CardHeader>
          <CardContent>
            {selected ? (
              <SpanInspector span={selected} />
            ) : (
              <p className="text-sm text-muted-foreground">Select a node to inspect its input and output.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
