'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { EmbeddingsHeader, type EmbeddingsMode } from './components/EmbeddingsHeader';
import { LookupWordsGrid } from './components/LookupWordsGrid';
import { RecordsGrid } from './components/RecordsGrid';
import { TryPhraseCard } from './components/TryPhraseCard';
import {
  useEmbedMissing,
  useEmbeddingsOverview,
  useLookupWords,
  useRecordsBackfill,
  useTryPhrase,
} from './hooks/useEmbeddings';
import { LIST_TABS, arrowTabs } from './lib';

/** System > Embeddings: every lookup word and business record the system embeds, and its vector. */
export default function EmbeddingsPage() {
  const [mode, setMode] = useState<EmbeddingsMode>('lookup');
  const [list, setList] = useState('category');
  const overview = useEmbeddingsOverview({ poll: mode === 'records' });

  const words = useLookupWords(list);
  const tryPhrase = useTryPhrase();
  const embedMissing = useEmbedMissing();
  const backfill = useRecordsBackfill();

  return (
    <>
      <EmbeddingsHeader
        overview={overview.data}
        loading={overview.isLoading}
        mode={mode}
        onEmbedMissing={() => embedMissing.mutate()}
        embedPending={embedMissing.isPending}
        onStartBackfill={() => backfill.mutate({ action: 'start' })}
        backfillPending={backfill.isPending}
      />
      <Container className="space-y-5">
        {overview.isError ? (
          <p className="text-sm text-destructive">
            {overview.error instanceof Error ? overview.error.message : 'Could not load embeddings.'}
          </p>
        ) : null}
        <Tabs value={mode} onValueChange={(v) => setMode(v as EmbeddingsMode)}>
          <TabsList variant="line" onKeyDown={arrowTabs(['lookup', 'records'], mode, (v) => setMode(v as EmbeddingsMode))}>
            <TabsTrigger value="lookup" onClick={() => setMode('lookup')}>
              Lookup words
            </TabsTrigger>
            <TabsTrigger value="records" onClick={() => setMode('records')}>
              Records
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {mode === 'lookup' ? (
          <>
            <TryPhraseCard
              result={tryPhrase.data}
              pending={tryPhrase.isPending}
              onTry={(phrase) => tryPhrase.mutate(phrase)}
            />
            <Tabs value={list} onValueChange={setList}>
              <TabsList variant="line" onKeyDown={arrowTabs(LIST_TABS.map((t) => t.value), list, setList)}>
                {LIST_TABS.map((t) => (
                  <TabsTrigger key={t.value} value={t.value} onClick={() => setList(t.value)}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <LookupWordsGrid
              rows={words.data?.rows ?? []}
              isLoading={words.isLoading}
              error={words.error}
              onRetry={'refetch' in words ? () => void (words as { refetch: () => void }).refetch() : undefined}
            />
          </>
        ) : overview.data ? (
          <>
            {overview.data.guard.running ? (
              <div className="flex justify-end">
                <Button variant="outline" onClick={() => backfill.mutate({ action: 'stop' })} disabled={backfill.isPending}>
                  Stop
                </Button>
              </div>
            ) : null}
            <RecordsGrid overview={overview.data} />
          </>
        ) : null}
      </Container>
    </>
  );
}
