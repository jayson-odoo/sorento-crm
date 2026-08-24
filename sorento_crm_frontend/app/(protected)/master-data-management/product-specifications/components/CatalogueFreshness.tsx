'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getCatalogueStatus, rereadCatalogue } from '../services/productSpecService';
import type { CatalogueStatus } from '../services/productSpecService';

/**
 * Whether the stored specifications were read with the rules that are live now.
 *
 * Editing a rule changes how a product WOULD be read. It does not change the 22,805
 * values already stored - those were read under the old rules and stay that way until
 * the catalogue is read again. Without this, a rule saves, the screen says saved, every
 * search keeps returning the old answer, and the only reasonable conclusion is that the
 * setting does nothing.
 */
export default function CatalogueFreshness({ refreshKey = 0 }: { refreshKey?: number }) {
  const [state, setState] = useState<CatalogueStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async () => {
    try {
      const next = await getCatalogueStatus();
      setState(next);
      // Only while there is something to watch. Polling an idle screen forever is a
      // request every few seconds for an answer nobody is waiting on.
      if (next.status === 'running') {
        timer.current = setTimeout(poll, 3000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read the catalogue status');
    }
  }, []);

  // `refreshKey` changes whenever a rule is saved: the rules moved, so this line is
  // stale until it asks again.
  useEffect(() => {
    poll();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [poll, refreshKey]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      await rereadCatalogue();
      await poll();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start reading the catalogue');
    } finally {
      setStarting(false);
    }
  };

  if (error) {
    return (
      <Alert variant="destructive" className="mb-4">
        <AlertIcon />
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    );
  }
  if (!state) return null;

  const running = state.status === 'running';
  const stale = state.rules_changed_since_last_read;
  const failed = state.status === 'failed';

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border p-3">
      {/* Never claim freshness that has not been established: before a first read
          there is no fingerprint to compare against, and "Up to date" beside "it is not
          known" is a label contradicting its own sentence. */}
      <Badge
        variant={
          running ? 'info' : failed ? 'destructive' : stale ? 'warning' : !state.ever_read ? 'secondary' : 'success'
        }
        appearance="light"
        shape="circle"
      >
        {running
          ? 'Reading'
          : failed
            ? 'Failed'
            : stale
              ? 'Out of date'
              : state.ever_read
                ? 'Up to date'
                : 'Not checked'}
      </Badge>

      <p className="min-w-0 flex-1 text-sm text-muted-foreground">
        {running &&
          'Reading every product with the current rules. This takes a few minutes; you can leave the page.'}
        {!running && failed &&
          `The last read did not finish: ${state.result?.error ?? 'unknown error'}`}
        {!running && !failed && stale &&
          'The rules have changed since the products were last read, so searches are still using the old values. Read the catalogue again to apply them.'}
        {!running && !failed && !stale && state.ever_read &&
          `Products were last read with the current rules${
            state.result?.written ? ` - ${state.result.written.toLocaleString()} rows` : ''
          }.`}
        {!running && !failed && !stale && !state.ever_read &&
          'Products have not been read from this screen yet, so it is not known whether the stored values match the current rules.'}
      </p>

      <Button size="sm" variant={stale ? 'primary' : 'outline'} onClick={start} disabled={running || starting}>
        {running ? 'Reading…' : 'Read the catalogue again'}
      </Button>
    </div>
  );
}
