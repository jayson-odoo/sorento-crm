'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  getFindabilityRun,
  getFindabilityRuns,
  getFlyers,
  runFindability,
} from '../services/productSpecService';
import { FindabilityResult, FindabilityRun } from '../types/productSpec.types';

type Flyer = {
  source_id: string;
  source_label: string;
  cards: number;
  last_run: string | null;
};

/** How the boundary reads to a person, and how alarming it is. */
function boundaryLabel(boundary: string): { text: string; tone: 'ok' | 'warn' | 'bad' } {
  if (boundary === 'none') return { text: 'Not found at all', tone: 'bad' };
  if (boundary === 'all') return { text: 'Only with every spec', tone: 'warn' };
  if (boundary === 'card') return { text: "From the card's words", tone: 'ok' };
  return { text: `From "${boundary.replace('one:', '').replace(/_/g, ' ')}" alone`, tone: 'ok' };
}

export default function FindabilityPanel() {
  const [flyers, setFlyers] = useState<Flyer[]>([]);
  const [sourceId, setSourceId] = useState<string>('');
  const [runs, setRuns] = useState<FindabilityRun[]>([]);
  const [run, setRun] = useState<FindabilityRun | null>(null);
  const [results, setResults] = useState<FindabilityResult[]>([]);
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFlyers()
      .then((data) => {
        setFlyers(data.flyers);
        if (data.flyers.length && !sourceId) setSourceId(data.flyers[0].source_id);
      })
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRuns = useCallback(async (id: string) => {
    const data = await getFindabilityRuns(id || undefined);
    setRuns(data.runs);
    if (data.runs.length) {
      const detail = await getFindabilityRun(data.runs[0].id);
      setRun(detail.run);
      setResults(detail.results);
    } else {
      setRun(null);
      setResults([]);
    }
  }, []);

  useEffect(() => {
    if (sourceId) loadRuns(sourceId).catch((e) => setError(e.message));
  }, [sourceId, loadRuns]);

  const refresh = useCallback(async () => {
    if (!run) return;
    const detail = await getFindabilityRun(run.id, {
      boundary: onlyGaps ? 'none' : undefined,
      q: query || undefined,
    });
    setResults(detail.results);
  }, [run, onlyGaps, query]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  async function sweep() {
    setBusy(true);
    setError(null);
    try {
      await runFindability({ sourceId });
      await loadRuns(sourceId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // The sweep runs in the background, so the totals climb while you watch. Polling
  // stops as soon as it finishes.
  useEffect(() => {
    if (run?.status !== 'running') return;
    const timer = setInterval(() => {
      loadRuns(sourceId).catch(() => undefined);
    }, 5000);
    return () => clearInterval(timer);
  }, [run?.status, sourceId, loadRuns]);

  const previous = runs.length > 1 ? runs[1] : null;
  const delta = run && previous ? run.not_found - previous.not_found : null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Can a customer find these products?</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Reads every card in a flyer, says what is printed on it, and checks that the
            product on that card comes back. Each product is asked for several ways — from
            its printed words, from every spec at once, and from each spec on its own — so
            the answer is where the boundary sits, not just pass or fail.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {/* The design system has no select primitive; the native control keeps
                this one screen from inventing a component the rest of the app lacks. */}
            <select
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              aria-label="Flyer"
              className="h-9 w-[380px] rounded-md border border-input bg-background px-3 text-sm"
            >
              {flyers.map((f) => (
                <option key={f.source_id} value={f.source_id}>
                  {f.source_label} ({f.cards} cards)
                </option>
              ))}
            </select>
            <Button onClick={sweep} disabled={busy || !sourceId || run?.status === 'running'}>
              {run?.status === 'running'
                ? `Checking… ${run.cards} cards so far`
                : busy
                  ? 'Starting…'
                  : 'Check this flyer'}
            </Button>
            {run?.status === 'running' ? (
              <span className="text-sm text-muted-foreground">
                A full flyer takes about half an hour. The totals below fill in as it goes.
              </span>
            ) : null}
            {run?.status === 'failed' ? (
              <span className="text-sm text-destructive">
                The last check stopped early: {run.error}
              </span>
            ) : null}
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          {run ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Cards checked" value={run.cards} />
              <Stat
                label="Found from the card's words"
                value={`${run.found_by_card} (${pct(run.found_by_card, run.cards)})`}
              />
              <Stat
                label="Found from its specs"
                value={`${run.found_by_specs} (${pct(run.found_by_specs, run.cards)})`}
              />
              <Stat
                label="Not found at all"
                value={run.not_found}
                hint={
                  delta === null
                    ? undefined
                    : delta === 0
                      ? 'unchanged since the last check'
                      : delta < 0
                        ? `${Math.abs(delta)} fewer than last time`
                        : `${delta} more than last time`
                }
                tone={run.not_found > 0 ? 'bad' : 'ok'}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No check has been run for this flyer yet.
            </p>
          )}
        </CardContent>
      </Card>

      {run ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>Card by card</CardTitle>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Find a product code"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-56"
              />
              <Button
                variant={onlyGaps ? 'primary' : 'outline'}
                onClick={() => setOnlyGaps((v) => !v)}
              >
                {onlyGaps ? 'Showing gaps only' : 'Show gaps only'}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Product</th>
                    <th className="py-2 pr-4 font-medium">What the card says</th>
                    <th className="py-2 pr-4 font-medium">Found by</th>
                    <th className="py-2 font-medium">Where it landed</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => {
                    const label = boundaryLabel(r.boundary);
                    return (
                      <tr key={r.product_code} className="border-t align-top">
                        <td className="py-2 pr-4 font-mono text-xs">
                          {r.product_code}
                          {r.is_discontinued ? (
                            <Badge variant="secondary" className="ml-2">
                              discontinued
                            </Badge>
                          ) : null}
                        </td>
                        <td className="max-w-[420px] py-2 pr-4 text-muted-foreground">
                          {r.phrase}
                        </td>
                        <td className="py-2 pr-4">
                          <Badge
                            variant={
                              label.tone === 'bad'
                                ? 'destructive'
                                : label.tone === 'warn'
                                  ? 'secondary'
                                  : 'success'
                            }
                          >
                            {label.text}
                          </Badge>
                        </td>
                        <td className="py-2">
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(r.ranks).map(([angle, rank]) => (
                              <span
                                key={angle}
                                className={`rounded px-1.5 py-0.5 text-xs ${
                                  rank
                                    ? 'bg-muted text-foreground'
                                    : 'bg-destructive/10 text-destructive'
                                }`}
                                title={angleHint(angle)}
                              >
                                {angleName(angle)} {rank ? `#${rank}` : '—'}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {results.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-muted-foreground">
                        Nothing to show. Every card in this flyer was found.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function pct(part: number, whole: number): string {
  if (!whole) return '—';
  return `${Math.round((part / whole) * 1000) / 10}%`;
}

function angleName(angle: string): string {
  if (angle === 'card') return 'card words';
  if (angle === 'all') return 'all specs';
  if (angle.startsWith('one:')) return angle.slice(4).replace(/_/g, ' ');
  if (angle.startsWith('without:')) return `no ${angle.slice(8).replace(/_/g, ' ')}`;
  return angle;
}

function angleHint(angle: string): string {
  if (angle === 'card') return "Asked using the card's printed words";
  if (angle === 'all') return 'Asked using every spec the flyer states';
  if (angle.startsWith('one:')) return `Asked using only ${angle.slice(4)}`;
  if (angle.startsWith('without:'))
    return `Asked using every spec except ${angle.slice(8)} — a miss here means that spec is doing the work`;
  return angle;
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'ok' | 'bad';
}) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={`text-xl font-semibold ${tone === 'bad' ? 'text-destructive' : ''}`}
      >
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
