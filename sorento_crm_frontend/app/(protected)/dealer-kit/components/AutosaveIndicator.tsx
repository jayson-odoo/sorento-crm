'use client';

/**
 * "Saving.../Saved <time>/Save failed (retry)" next to a host's own manual
 * Save button (D22, S8) - what `useAutosave` reports, read by whichever
 * editor is autosaving (the request tag designer, the template editor).
 *
 * `idle` renders nothing: nothing has changed since the doc was loaded, so
 * there is nothing to say yet - the manual Save button is not made to look
 * unfinished just because autosave has not had a reason to run.
 */

import { Button } from '@/components/ui/button';
import type { AutosaveStatus } from '@/hooks/useAutosave';

function formatSavedAt(savedAt: Date): string {
  return savedAt.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function AutosaveIndicator({
  status,
  savedAt,
  onRetry,
  className,
}: {
  status: AutosaveStatus;
  savedAt: Date | null;
  onRetry?: () => void;
  className?: string;
}) {
  if (status === 'idle') return null;

  if (status === 'saving') {
    return <span className={className ?? 'text-xs text-muted-foreground'}>Saving...</span>;
  }

  if (status === 'error') {
    return (
      <span className={className ?? 'flex items-center gap-1 text-xs text-destructive'}>
        Save failed
        {onRetry && (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs text-destructive underline"
            onClick={onRetry}
          >
            Retry
          </Button>
        )}
      </span>
    );
  }

  // 'saved'
  return (
    <span className={className ?? 'text-xs text-muted-foreground'}>
      Saved{savedAt ? ` ${formatSavedAt(savedAt)}` : ''}
    </span>
  );
}
