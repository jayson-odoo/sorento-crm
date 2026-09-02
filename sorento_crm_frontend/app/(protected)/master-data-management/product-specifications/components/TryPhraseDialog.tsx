'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { previewSpecSearch } from '../services/productSpecService';
import type { SpecPreviewResult } from '../types/productSpec.types';

/**
 * Judge the ranker by using it (AC-A.6).
 *
 * Kept in component state rather than the URL: closing the dialog does not clear
 * the last run, re-opening shows it again, and only leaving the page drops it.
 */
export function TryPhraseDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [phrase, setPhrase] = useState('');
  const [result, setResult] = useState<SpecPreviewResult | null>(null);
  const [ranPhrase, setRanPhrase] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    const trimmed = phrase.trim();
    setLoading(true);
    setError(null);
    try {
      const terms = trimmed ? trimmed.split(/\s+/) : [];
      const next = await previewSpecSearch({
        specs: [],
        free_terms: trimmed ? [trimmed, ...terms] : [],
        phrase: trimmed || undefined,
        understand: true,
      });
      setResult(next);
      setRanPhrase(trimmed);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Try a phrase</DialogTitle>
          <DialogDescription>
            Type what a customer would say and see what the engine understood.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1">
              <Input
                id="try-phrase"
                aria-label="Customer phrase"
                value={phrase}
                placeholder="stainless steel kitchen sink"
                onChange={(e) => setPhrase(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void run();
                }}
              />
            </div>
            <Button onClick={() => void run()} disabled={loading}>
              {loading ? 'Searching...' : 'Search'}
            </Button>
          </div>

          {!loading && result?.understanding && (
            <div className="flex flex-col gap-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  Understood as
                </span>
                <Badge
                  variant={result.understanding.source === 'semantic' ? 'success' : 'secondary'}
                  size="sm"
                  appearance="light"
                  shape="circle"
                >
                  {result.understanding.source === 'semantic'
                    ? (result.understanding.model ?? 'semantic')
                    : 'literal words only'}
                </Badge>
              </div>
              {result.understanding.specs.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {result.understanding.specs.map((spec) => (
                    <Badge key={spec.key} variant="outline" size="sm" appearance="light" shape="circle">
                      {spec.key.replace(/_/g, ' ')} = {String(spec.value)}
                    </Badge>
                  ))}
                </div>
              )}
              {(result.understanding.exclusions?.length ?? 0) > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground">
                    Ruled out
                  </span>
                  {result.understanding.exclusions.map((spec) => (
                    <Badge
                      key={`${spec.key}-${String(spec.value)}`}
                      variant="destructive"
                      size="sm"
                      appearance="light"
                      shape="circle"
                    >
                      {spec.key.replace(/_/g, ' ')} ≠ {String(spec.value)}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertIcon />
              <AlertTitle>{error}</AlertTitle>
            </Alert>
          )}

          {loading && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}

          {!loading && result && result.candidates.length === 0 && (
            <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              No product matched &ldquo;{ranPhrase}&rdquo;.
            </div>
          )}

          {!loading && result && result.candidates.length > 0 && (
            <div className="flex flex-col gap-2">
              {result.unmet?.length > 0 && (
                <Alert variant="warning">
                  <AlertIcon />
                  <AlertTitle>
                    Nothing here is{' '}
                    {result.unmet.map((u) => String(u.value).replace(/_/g, ' ')).join(' or ')}.
                    These are the closest the catalogue has.
                  </AlertTitle>
                </Alert>
              )}
              {result.candidates.map((candidate, index) => (
                <Link
                  key={candidate.product_id}
                  href={`/master-data-management/products/${candidate.product_id}?tab=specifications`}
                  className="flex flex-col gap-2 rounded-md border p-3 hover:bg-muted/40 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-muted-foreground">{index + 1}.</span>
                      <span className="font-mono font-semibold">{candidate.product_code}</span>
                      {candidate.is_discontinued && (
                        <Badge variant="warning" size="sm" appearance="light" shape="circle">
                          Discontinued
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1 break-words text-sm text-muted-foreground">
                      {candidate.summary || 'No specification text'}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                    {candidate.matched_specs.map((key) => (
                      <Badge key={key} variant="success" size="sm" appearance="light" shape="circle">
                        {key.replace(/_/g, ' ')}
                      </Badge>
                    ))}
                    <span className="font-mono text-sm tabular-nums" title="Total ranking score">
                      {candidate.score}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {!loading && !result && !error && (
            <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              Type what a customer would send.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default TryPhraseDialog;
