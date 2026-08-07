'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { getSpecRegistry, previewSpecSearch } from '../services/productSpecService';
import type { SpecPreviewResult, SpecRegistryKey } from '../types/productSpec.types';

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
  const [registry, setRegistry] = useState<SpecRegistryKey[]>([]);
  const [phrase, setPhrase] = useState('');
  const [specs, setSpecs] = useState<{ key: string; value: string }[]>([]);
  const [includeAccessories, setIncludeAccessories] = useState(false);
  // Off shows the literal reading alone. Useful for telling "the ranking is wrong"
  // apart from "the phrase was misunderstood", which look identical from the results.
  const [semantic, setSemantic] = useState(true);
  const [result, setResult] = useState<SpecPreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSpecRegistry()
      .then((r) => setRegistry(r.keys))
      .catch((e) => setError(e.message));
  }, []);

  const enumKeys = registry.filter(
    (k) => k.data_type === 'enum' && (k.allowed_values?.length ?? 0) > 0,
  );

  const setSpec = (key: string, value: string) => {
    setSpecs((current) => {
      const rest = current.filter((s) => s.key !== key);
      return value ? [...rest, { key, value }] : rest;
    });
  };

  const valueFor = (key: string) => specs.find((s) => s.key === key)?.value ?? '';
  const pinnedCount = specs.filter((s) => s.value).length;

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const terms = phrase.trim() ? phrase.trim().split(/\s+/) : [];
      setResult(
        await previewSpecSearch({
          specs: specs.map((s) => ({ key: s.key, value: s.value })),
          // The whole phrase AND its words: the ranker resolves a class synonym from
          // either, and this mirrors what the parser hands over.
          free_terms: phrase.trim() ? [phrase.trim(), ...terms] : [],
          include_accessories: includeAccessories,
          // Read semantically as well as literally, so a typo or an unusual phrasing
          // still lands on the right spec.
          phrase: phrase.trim() || undefined,
          understand: semantic,
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
    setSpecs([]);
    setResult(null);
    setError(null);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Try a customer phrase</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <p className="text-sm text-muted-foreground max-w-2xl">
          Type what a customer would send, optionally pin the specs the parser would
          extract, and see exactly what the chatbot would offer back. Scores and matched
          keys are shown so a wrong result can be explained.
        </p>

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
          Folded away by default. Once the sentence is understood, these are no longer
          how you search — they are how you PIN a value to prove the ranker wrong
          independently of the reading. That is a debugging job, not the main one, and a
          nine-dropdown band across the top implied otherwise.
        */}
        {enumKeys.length > 0 && (
          <details className="rounded-md border px-3 py-2">
            <summary className="cursor-pointer text-sm text-muted-foreground">
              Pin a spec by hand
              {pinnedCount > 0 && (
                <Badge variant="primary" size="sm" className="ml-2">
                  {pinnedCount}
                </Badge>
              )}
            </summary>
            <p className="text-xs text-muted-foreground mt-2">
              Overrides what was understood from the phrase, so you can test the ranking
              on its own.
            </p>
            <div className="flex flex-wrap gap-3 mt-3">
              {enumKeys.map((key) => (
                <div key={key.spec_key} className="min-w-[10rem]">
                  <label
                    htmlFor={`spec-${key.spec_key}`}
                    className="text-xs uppercase tracking-wide text-muted-foreground mb-1 block"
                  >
                    {key.label}
                  </label>
                  <select
                    id={`spec-${key.spec_key}`}
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={valueFor(key.spec_key)}
                    onChange={(e) => setSpec(key.spec_key, e.target.value)}
                  >
                    <option value="">Any</option>
                    {key.allowed_values.map((value) => (
                      <option key={value} value={value}>
                        {value.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </details>
        )}

        <div className="flex flex-wrap items-center gap-5">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeAccessories}
              onChange={(e) => setIncludeAccessories(e.target.checked)}
            />
            Include accessories and spare parts
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={semantic}
              onChange={(e) => setSemantic(e.target.checked)}
            />
            Understand the sentence
            <span className="text-muted-foreground">
              (off = match words literally)
            </span>
          </label>
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
                  <Badge key={spec.key} variant="outline" size="sm">
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
                      <Badge variant="warning" size="sm">
                        Discontinued
                      </Badge>
                    )}
                    {candidate.is_accessory && (
                      <Badge variant="secondary" size="sm">
                        Accessory
                      </Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground break-words mt-1">
                    {candidate.summary || 'No specification text'}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  {candidate.matched_specs.map((key) => (
                    <Badge key={key} variant="success" size="sm">
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
            <p className="text-xs text-muted-foreground">
              Click any result to see every spec it carries and the text each one was read
              from.
            </p>
          </div>
        )}

        {!loading && !result && !error && (
          <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            No search run yet. Try &quot;stainless steel kitchen sink&quot;, &quot;black
            sink&quot;, or something absurd like &quot;quantum toaster&quot; to see the
            floor refuse it.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
