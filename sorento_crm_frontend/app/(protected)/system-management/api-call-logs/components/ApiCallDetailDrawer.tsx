'use client';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { ApiCallLogRow } from '../types/apiCallLog.types';

function prettyJson(raw: string | null): string | null {
  if (!raw) return null;
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    // Not JSON (form-encoded, plain text, an HTML error page). Show it as-is
    // rather than hiding a body we could not parse.
    return raw;
  }
}

function PayloadBlock({ label, raw }: { label: string; raw: string | null }) {
  const body = prettyJson(raw);
  return (
    <section className="space-y-1.5">
      <h3 className="text-xs font-medium text-muted-foreground">{label}</h3>
      {body ? (
        <pre className="max-h-80 overflow-auto rounded bg-muted/50 p-3 text-[11px] leading-relaxed">
          {body}
        </pre>
      ) : (
        // An explicit reason, not a blank space: an empty body and a pruned body
        // look identical otherwise, and only one of them is a problem.
        <p className="rounded bg-muted/30 p-3 text-xs text-muted-foreground">
          No body recorded - the request had none, or the payload has passed its
          30-day retention window and was cleared.
        </p>
      )}
    </section>
  );
}

export function ApiCallDetailDrawer({
  row,
  onClose,
}: {
  row: ApiCallLogRow | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={!!row} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        {row && (
          <>
            <SheetHeader>
              <SheetTitle className="break-all text-sm">
                {row.method} {row.endpoint}
              </SheetTitle>
              <SheetDescription>
                {row.source} · {formatDateTimeInMalaysia(row.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-5 overflow-y-auto px-5 pb-8">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                <div>
                  <dt className="text-muted-foreground">Source</dt>
                  <dd className="mt-0.5">
                    <Badge variant="secondary" appearance="light" size="sm">
                      {row.source}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Outcome</dt>
                  <dd className="mt-0.5">
                    <Badge
                      variant={row.outcome === 'success' ? 'success' : 'destructive'}
                      appearance="light"
                      size="sm"
                    >
                      {row.status_code ?? '-'} {row.outcome}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Latency</dt>
                  <dd className="mt-0.5">{row.latency_ms ?? '-'} ms</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">When</dt>
                  <dd className="mt-0.5">{formatDateTimeInMalaysia(row.created_at)}</dd>
                </div>
                {row.tool_name && (
                  <div>
                    <dt className="text-muted-foreground">MCP tool</dt>
                    <dd className="mt-0.5 font-mono">{row.tool_name}</dd>
                  </div>
                )}
                {row.correlation_id && (
                  <div className="col-span-2">
                    <dt className="text-muted-foreground">Correlation id</dt>
                    <dd className="mt-0.5 break-all font-mono">{row.correlation_id}</dd>
                  </div>
                )}
              </dl>

              {row.error_message && (
                <section className="space-y-1.5">
                  <h3 className="text-xs font-medium text-muted-foreground">Error</h3>
                  <pre className="overflow-auto rounded bg-destructive/10 p-3 text-[11px] text-destructive">
                    {row.error_message}
                  </pre>
                </section>
              )}

              <PayloadBlock label="Request payload" raw={row.request_payload} />
              <PayloadBlock label="Response payload" raw={row.response_payload} />

              <p className="text-[11px] text-muted-foreground">
                Payloads are redacted (secret-keyed fields removed) and truncated to 8KB.
              </p>
            </div>

            <div className="border-t px-5 py-3">
              <Button variant="outline" size="sm" onClick={onClose}>
                Close
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
