'use client';

import { Badge, type BadgeProps } from '@/components/ui/badge';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import type { SpanExtract, SpanExtractSource } from '../types/chatbotTurn.types';

const SOURCE_VARIANT: Record<SpanExtractSource, BadgeProps['variant']> = {
  span: 'primary',
  near_exact: 'warning',
  held: 'success',
  number: 'secondary',
};

/** The span pass of a turn, in the Index match section's own heading, chip and muted-text styles. */
export function SpanPassSection({
  spanExtract,
  promptText = null,
}: {
  spanExtract: SpanExtract;
  promptText?: string | null;
}) {
  const model = [spanExtract.provider, spanExtract.model].filter(Boolean).join(' / ');
  const tokens = spanExtract.tokens ?? {};
  return (
    <div className="space-y-3" data-testid="span-pass">
      <p className="text-xs text-muted-foreground" data-testid="span-pass-call">
        {[
          model || 'No span model',
          spanExtract.model_source,
          `${spanExtract.ms} ms`,
          `${tokens.prompt_tokens ?? 0} in`,
          `${tokens.completion_tokens ?? 0} out`,
        ]
          .filter(Boolean)
          .join(' | ')}
      </p>
      {spanExtract.fallback && (
        <p className="text-xs text-muted-foreground">
          The span pass fell back to the plain word lookup
          {spanExtract.fallback_reason ? `: ${spanExtract.fallback_reason}` : ''}.
        </p>
      )}
      <div className="space-y-1 text-xs">
        <div className="text-2xs font-medium text-muted-foreground">Phrases copied from the message</div>
        {spanExtract.spans.length === 0 ? (
          <p className="text-muted-foreground">No phrase was copied.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {spanExtract.spans.map((s, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs">
                <span className="font-medium">{s.text}</span>
                {s.type && <span className="text-muted-foreground">{s.type}</span>}
                {s.status && (
                  <Badge variant="primary" size="sm">
                    {s.status}
                  </Badge>
                )}
                {s.residual && (
                  <Badge variant="warning" size="sm">
                    residual
                  </Badge>
                )}
              </span>
            ))}
          </div>
        )}
        {spanExtract.spans.some((s) => s.candidates?.length) && (
          <ul className="space-y-1 pt-1" data-testid="span-candidates">
            {spanExtract.spans.map((s, i) =>
              s.candidates?.length ? (
                <li key={i} className="min-w-0">
                  <span className="font-medium">{s.text}</span>
                  <span className="text-muted-foreground"> matched </span>
                  {s.candidates.map((c, j) => (
                    <span key={j} className="me-1 inline-flex items-center gap-1" title={c.label}>
                      <span>{c.label}</span>
                      <Badge variant="secondary" size="sm">
                        {c.signal} {c.score.toFixed(2)}
                      </Badge>
                    </span>
                  ))}
                </li>
              ) : null,
            )}
          </ul>
        )}
      </div>
      {(spanExtract.near_exact?.length ?? 0) > 0 && (
        <div className="space-y-1 text-xs" data-testid="span-near-exact">
          <div className="text-2xs font-medium text-muted-foreground">Added from the message spelling</div>
          <div className="flex flex-wrap gap-1">
            {spanExtract.near_exact?.map((n, i) => (
              <span
                key={i}
                data-testid="near-exact-label"
                className="min-w-0 whitespace-normal break-words rounded border border-warning/40 px-1.5 py-0.5 text-xs"
              >
                {n.label} <span className="text-muted-foreground">{n.spelling.toFixed(2)}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="space-y-1 text-xs">
        <div className="text-2xs font-medium text-muted-foreground">Handed to the parser</div>
        {Object.keys(spanExtract.final_block ?? {}).length > 0 ? (
          <div className="space-y-1">
            {Object.entries(spanExtract.final_block ?? {}).map(([list, rows]) => (
              <div key={list} className="flex flex-wrap items-center gap-1">
                <span className="text-muted-foreground">{list}</span>
                {rows.map((r, i) => (
                  <span key={i} data-testid={`final-source-${r.source}`} className="inline-flex items-center gap-1">
                    <span>{r.label}</span>
                    <Badge variant={SOURCE_VARIANT[r.source]} size="sm">
                      {r.source === 'near_exact' ? 'spelling' : r.source}
                    </Badge>
                  </span>
                ))}
              </div>
            ))}
          </div>
        ) : spanExtract.matched_rows.length === 0 ? (
          <p className="text-muted-foreground">No rows were shown.</p>
        ) : (
          <ul className="space-y-0.5">
            {spanExtract.matched_rows.map((r) => (
              <li key={r} className="truncate" title={r}>
                {r}
              </li>
            ))}
          </ul>
        )}
      </div>
      {promptText && (
        <Collapsible>
          <CollapsibleTrigger className="text-xs text-primary underline-offset-2 hover:underline">
            Prompt text sent to the parser
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-1 overflow-x-auto">
              <SearchableCode text={promptText} />
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
