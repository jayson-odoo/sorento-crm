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
import type { ClientErrorRow } from './services/clientErrorService';

function Field({ label, value, mono }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`mt-0.5 break-all ${mono ? 'font-mono' : ''}`}>{value || '-'}</dd>
    </div>
  );
}

export function ClientErrorDetailDrawer({
  row,
  onClose,
}: {
  row: ClientErrorRow | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={!!row} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-2xl">
        {row && (
          <>
            <SheetHeader>
              <SheetTitle className="break-all text-sm">
                {row.error_name ?? 'Error'}: {row.message ?? ''}
              </SheetTitle>
              <SheetDescription>
                {row.user_name ?? 'Unknown user'} · {formatDateTimeInMalaysia(row.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-5 overflow-y-auto px-5 pb-8">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                <div>
                  <dt className="text-muted-foreground">Screen</dt>
                  <dd className="mt-0.5">
                    <Badge
                      variant={row.boundary === 'global' ? 'destructive' : 'warning'}
                      appearance="light"
                      size="sm"
                    >
                      {row.boundary === 'global' ? 'App could not start' : 'Page error'}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Kind</dt>
                  <dd className="mt-0.5">
                    <Badge variant={row.is_chunk_error ? 'info' : 'secondary'} appearance="light" size="sm">
                      {row.is_chunk_error ? 'Stale build (chunk load)' : 'Error'}
                    </Badge>
                  </dd>
                </div>
                <Field label="Page" value={row.path} mono />
                <Field label="Reference" value={row.digest} mono />
                <Field label="Build" value={row.build_sha} mono />
                <Field
                  label="Browser time"
                  value={row.client_ts ? formatDateTimeInMalaysia(row.client_ts) : null}
                />
                <div className="col-span-2">
                  <Field label="Browser" value={row.user_agent} />
                </div>
              </dl>

              <section className="space-y-1.5">
                <h3 className="text-xs font-medium text-muted-foreground">Stack</h3>
                {row.stack ? (
                  <pre className="max-h-96 overflow-auto rounded bg-muted/50 p-3 text-2xs leading-relaxed">
                    {row.stack}
                  </pre>
                ) : (
                  <p className="rounded bg-muted/30 p-3 text-xs text-muted-foreground">
                    No stack recorded.
                  </p>
                )}
              </section>
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
