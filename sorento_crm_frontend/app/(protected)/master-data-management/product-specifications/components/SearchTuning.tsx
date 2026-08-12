'use client';

import { useEffect, useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { getSearchPolicy, updateSearchPolicy } from '../services/productSpecService';
import type { SpecSearchPolicyRow } from '../types/productSpec.types';

/**
 * How heavily the ranker weighs each thing.
 *
 * These were constants in the code, which put "discontinued products should rank
 * lower" behind a deploy. Each row says what it does in the language of the decision
 * being made, not the language of the scoring function — someone tuning this is asking
 * a merchandising question, not reading an algorithm.
 */
export default function SearchTuning() {
  const [rows, setRows] = useState<SpecSearchPolicyRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSearchPolicy()
      .then((r) => {
        setRows(r.policy);
        setDrafts(Object.fromEntries(r.policy.map((p) => [p.policy_key, String(p.value)])));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const save = async (row: SpecSearchPolicyRow) => {
    setSaving(row.policy_key);
    setError(null);
    try {
      const saved = await updateSearchPolicy(row.policy_key, Number(drafts[row.policy_key]));
      setRows((current) =>
        current.map((r) => (r.policy_key === row.policy_key ? { ...r, value: saved.value } : r)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>How results are ranked</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && (
          <Alert variant="destructive">
            <AlertIcon />
            <AlertTitle>{error}</AlertTitle>
          </Alert>
        )}

        {loading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : (
          rows.map((row) => {
            const draft = drafts[row.policy_key] ?? '';
            const dirty = Number(draft) !== row.value;
            return (
              <div
                key={row.policy_key}
                className="flex flex-col gap-2 border-b pb-3 last:border-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {row.label}
                    {row.value !== row.default_value && (
                      <Badge variant="secondary" size="sm" appearance="light" shape="circle">
                        Changed from {row.default_value}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{row.help_text}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Input
                    type="number"
                    step="0.5"
                    min="0"
                    className="w-24 tabular-nums"
                    value={draft}
                    onChange={(e) =>
                      setDrafts((current) => ({ ...current, [row.policy_key]: e.target.value }))
                    }
                  />
                  <Button
                    size="sm"
                    variant={dirty ? 'primary' : 'outline'}
                    disabled={!dirty || saving === row.policy_key}
                    onClick={() => save(row)}
                  >
                    {saving === row.policy_key ? 'Saving…' : 'Save'}
                  </Button>
                </div>
              </div>
            );
          })
        )}

        <p className="text-xs text-muted-foreground">
          Every number here is a nudge, never a filter. A product that answers the question
          is always offered — these decide the order it is offered in. To prefer a
          particular brand, edit that key below and set a preference against its values.
        </p>
      </CardContent>
    </Card>
  );
}
