'use client';

import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * The "error" final state of NEVER-STUCK-UI S3: a short heading, the reason, and
 * a Retry that actually refetches. Used where a read failed for a reason that is
 * neither "no access" (render `AccessDenied`) nor "not found".
 */
export default function LoadErrorState({
  title,
  message,
  onRetry,
  retrying = false,
  className,
}: {
  title: string;
  /** User-facing reason, e.g. from `extractApiError`. Omit when there is none worth showing. */
  message?: string;
  onRetry: () => void;
  /** True while the retry is in flight, so a second click cannot stack requests. */
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center px-4 py-10 text-center',
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <AlertCircle className="h-6 w-6 text-muted-foreground" />
      </div>
      <h2 className="mt-4 text-base font-semibold text-foreground">{title}</h2>
      {message ? (
        <p className="mt-1 max-w-md break-words text-sm text-muted-foreground">{message}</p>
      ) : null}
      <Button variant="outline" className="mt-4" onClick={onRetry} disabled={retrying}>
        <RefreshCw className={cn(retrying && 'animate-spin')} />
        Retry
      </Button>
    </div>
  );
}
