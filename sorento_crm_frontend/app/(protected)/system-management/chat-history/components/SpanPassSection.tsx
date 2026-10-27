'use client';

import { Badge } from '@/components/ui/badge';
import type { SpanExtract } from '../types/chatbotTurn.types';

/** The span pass of a turn, in the Index match section's own heading, chip and muted-text styles. */
export function SpanPassSection({ spanExtract }: { spanExtract: SpanExtract }) {
  return (
    <div className="space-y-3" data-testid="span-pass">
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
      </div>
      <div className="space-y-1 text-xs">
        <div className="text-2xs font-medium text-muted-foreground">Rows shown to the parser</div>
        {spanExtract.matched_rows.length === 0 ? (
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
    </div>
  );
}
