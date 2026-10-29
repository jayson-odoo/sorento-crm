'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { wholeNumberRangeError } from '@/lib/whole-number-range';
import { useEmbeddingsOverview } from '@/app/(protected)/system-management/embeddings/hooks/useEmbeddings';

import { useEmbeddingSettings, useSaveEmbeddingSettings } from './hooks/useEmbeddingSettings';

const PROVIDERS = [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openai', label: 'OpenAI' },
];
const MODELS: Record<string, string[]> = {
  gemini: ['gemini-embedding-001'],
  openai: ['text-embedding-3-small', 'text-embedding-3-large'],
};
const num = (n: number) => n.toLocaleString('en-US');

/** Settings -> Embeddings: the one embedder for lookup words and records, and how fast a switch backfills. */
export default function EmbeddingsSettingsPage() {
  const settings = useEmbeddingSettings();
  const overview = useEmbeddingsOverview();
  const save = useSaveEmbeddingSettings();
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [rpm, setRpm] = useState<string>('');
  const [loaded, setLoaded] = useState(false);

  // Prefill waits for the overview to settle: a setting never saved shows the embedder that actually runs.
  // Only known values prefill: a setting never saved with no overview to say what runs stays blank, never a guess.
  const [initial, setInitial] = useState<{ provider: string; model: string }>({ provider: '', model: '' });
  const [resolved, setResolved] = useState<{ provider: string; model: string }>({ provider: '', model: '' });
  useEffect(() => {
    if (settings.data && !overview.isLoading && !loaded) {
      const p = settings.data.embedding_provider ?? overview.data?.setting.provider ?? '';
      const m = settings.data.embedding_model ?? overview.data?.setting.model ?? '';
      setProvider(p);
      setModel(m);
      setResolved({ provider: p, model: m });
      setInitial({ provider: settings.data.embedding_provider ?? '', model: settings.data.embedding_model ?? '' });
      setRpm(String(settings.data.embedding_backfill_rpm));
      setLoaded(true);
    }
  }, [settings.data, overview.isLoading, overview.data, loaded]);

  const modelOptions = useMemo(() => {
    const names = new Set([...(MODELS[provider] ?? []), ...(model ? [model] : [])]);
    return [...names].map((m) => ({ value: m, label: m }));
  }, [provider, model]);

  if (settings.isError && !loaded) {
    return <p className="text-sm text-destructive">Embedding settings could not be loaded. Reload the page to try again.</p>;
  }
  if (!loaded) return <Skeleton className="h-64 w-full" />;

  const rpmError = wholeNumberRangeError(rpm, 1, 600);
  const o = overview.isError ? undefined : overview.data; // no overview (403 or failure): the form stands alone
  const searchModel = o?.records_search_model ?? settings.data?.embedding_records_search_model ?? null;
  const targetChunks = o?.records.reduce((s, r) => s + (r.chunks_by_model[o.setting.model] ?? 0), 0) ?? 0;
  const searchChunks = o?.records.reduce((s, r) => s + (r.chunks_by_model[searchModel ?? o.records_search_model] ?? 0), 0) ?? 0;
  const pct = o && searchChunks > 0 ? Math.min(100, Math.round((targetChunks / searchChunks) * 100)) : 0;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Embeddings</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-5 py-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Provider</Label>
            <SearchableSelect
              value={provider}
              onChange={(v) => {
                setProvider(v);
                setModel(MODELS[v]?.[0] ?? '');
              }}
              options={PROVIDERS}
            />
          </div>
          <div className="space-y-2">
            <Label>Model</Label>
            <SearchableSelect value={model} onChange={setModel} options={modelOptions} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="embedding-backfill-rpm">Backfill requests per minute</Label>
            <NumberInput
              id="embedding-backfill-rpm"
              inputMode="numeric"
              value={rpm}
              error={rpmError}
              onChange={(e) => setRpm(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {o ? (
        <Card>
          <CardContent className="space-y-3 py-5 text-sm">
            <div className="flex flex-wrap items-baseline gap-x-3">
              <span className="w-32 text-muted-foreground">Lookup words</span>
              <span>
                {num(o.lookup.texts_with_vector)} / {num(o.lookup.texts_total)} with a {o.setting.model} vector
              </span>
            </div>
            {searchModel && searchModel !== o.setting.model ? (
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="w-32 text-muted-foreground">Record search</span>
                <span>
                  {searchModel}
                  {searchModel !== o.setting.model
                    ? ` · moves to ${o.setting.model} at 100% · ${num(targetChunks)} / ${num(searchChunks)} · ${pct}%`
                    : ''}
                </span>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <div className="flex justify-end">
        <Button
          onClick={() =>
            save.mutate({
              // What was saved before is sent as it was; a value that only stands in for "unknown" is not sent.
              ...(provider && (provider !== initial.provider || initial.provider) ? { embedding_provider: provider } : {}),
              ...(model && (model !== initial.model || initial.model) ? { embedding_model: model } : {}),
              embedding_backfill_rpm: Number(rpm),
              recordsBackfillStarted: !!model && (provider !== resolved.provider || model !== resolved.model),
            })
          }
          disabled={save.isPending || !!rpmError || (!!provider !== !!model)}
        >
          {save.isPending ? <LoaderCircleIcon className="animate-spin" /> : null}
          Save
        </Button>
      </div>
    </div>
  );
}
