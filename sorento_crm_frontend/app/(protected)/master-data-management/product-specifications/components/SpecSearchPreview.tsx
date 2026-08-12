'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { previewSpecSearch } from '../services/productSpecService';
import type { SpecPreviewResult } from '../types/productSpec.types';

/**
 * Judge the ranker by using it.
 *
 * The relevance floor and the per-key weights are one engineer's judgement measured
 * against a small eval set. They only become right when someone who sells this catalog
 * types real phrases and says which results are wrong, which is what this screen is
 * for. Each candidate shows its score and the keys it matched, so a wrong result can
 * be explained rather than only noticed.
 */
export default function SpecSearchPreview() {
  const [phrase, setPhrase] = useState('');
  const [result, setResult] = useState<SpecPreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);



  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const terms = phrase.trim() ? phrase.trim().split(/\s+/) : [];
      setResult(
        await previewSpecSearch({
          specs: [],
          // The whole phrase AND its words: the ranker resolves a class synonym from
          // either, and this mirrors what the parser hands over.
          free_terms: phrase.trim() ? [phrase.trim(), ...terms] : [],
          // Read semantically as well as literally, so a typo or an unusual phrasing
          // still lands on the right spec.
          phrase: phrase.trim() || undefined,
          // The sentence is ALWAYS read semantically: turning it off answered a
          // question nobody asks while typing a customer's words.
          understand: true,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Preview failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setPhrase('');
    setResult(null);
    setError(null);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Try a customer phrase</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 min-w-0">
            <label htmlFor="spec-phrase" className="text-sm font-medium mb-1.5 block">
              Customer phrase
            </label>
            <Input
              id="spec-phrase"
              value={phrase}
              placeholder="stainless steel kitchen sink"
              onChange={(e) => setPhrase(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') run();
              }}
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={run} disabled={loading}>
              {loading ? 'Searching...' : 'Search'}
            </Button>
            <Button variant="outline" onClick={reset} disabled={loading}>
              Reset
            </Button>
          </div>
        </div>

        {/*
          The hand-pinning panel and the "understand the sentence" switch both used to
          live here. Neither survived contact with the job: a customer types a sentence
          and the model always reads it, so a nine-dropdown override band and a toggle
          for turning the reading off were two ways of asking a question nobody has.
          Both are still reachable through the API for debugging a bad reading.
        */}

        {!loading && result?.understanding && (
          <div className="flex flex-col gap-2 rounded-md border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                Understood as
              </span>
              <Badge
                variant={result.understanding.source === 'semantic' ? 'success' : 'secondary'}
                size="sm" appearance="light" shape="circle"
              >
                {result.understanding.source === 'semantic'
                  ? result.understanding.model ?? 'semantic'
                  : 'literal words only'}
              </Badge>
              {result.understanding.elapsed_ms != null && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {result.understanding.elapsed_ms} ms
                </span>
              )}
            </div>
            {result.understanding.specs.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {result.understanding.specs.map((spec) => (
                  <Badge key={spec.key} variant="outline" size="sm" appearance="light" shape="circle">
                    {spec.key.replace(/_/g, ' ')} = {String(spec.value)}
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">
                No specification recognised — the results below come from the wording
                alone.
              </span>
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
                <span className="text-xs text-muted-foreground">
                  Products known to be this are removed, not just ranked lower.
                </span>
              </div>
            )}
            {result.understanding.notes && (
              <p className="text-xs text-muted-foreground">{result.understanding.notes}</p>
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
            <Skeleton className="h-12 w-full" />
          </div>
        )}

        {!loading && result?.floor_missed && (
          <Alert variant="warning">
            <AlertIcon />
            <AlertTitle>
              Nothing cleared the relevance floor (best score {result.top_score}, floor{' '}
              {result.floor}). The chatbot would show no products and ask for a code,
              model name or photo instead.
            </AlertTitle>
          </Alert>
        )}

        {!loading && result && !result.floor_missed && (
          <div className="flex flex-col gap-2">
            {result.unmet?.length > 0 && (
              <Alert variant="warning">
                <AlertIcon />
                <AlertTitle>
                  Nothing here is{' '}
                  {result.unmet
                    .map((u) => `${String(u.value).replace(/_/g, ' ')}`)
                    .join(' or ')}
                  . These are the closest the catalogue has — the chatbot says so rather
                  than substituting quietly.
                </AlertTitle>
              </Alert>
            )}
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              What the customer would see
            </div>
            {result.candidates.map((candidate, index) => (
              // Straight to that product's Specifications tab. The summary below is only
              // what the ranker MATCHED on — every other derived value, and the text each
              // was read from, is one click away.
              <Link
                key={candidate.product_id}
                href={`/master-data-management/products/${candidate.product_id}?tab=specifications`}
                className="flex flex-col gap-2 rounded-md border p-3 transition-colors hover:bg-muted/40 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground text-sm">{index + 1}.</span>
                    <span className="font-mono font-semibold">{candidate.product_code}</span>
                    {candidate.is_discontinued && (
                      <Badge variant="warning" size="sm" appearance="light" shape="circle">
                        Discontinued
                      </Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground break-words mt-1">
                    {candidate.summary || 'No specification text'}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  {candidate.matched_specs.map((key) => (
                    <Badge key={key} variant="success" size="sm" appearance="light" shape="circle">
                      {key.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                  <span
                    className="font-mono text-sm tabular-nums"
                    title="Total ranking score"
                  >
                    {candidate.score}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}

        {!loading && !result && !error && (
          <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            Type what a customer would send. Try &quot;quantum toaster&quot; to watch it
            refuse rather than guess.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
