'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { PageHeader } from '@/components/common/PageHeader';
import { useTownSnapshot } from '@/hooks/useTownSnapshot';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { isPending } from '@/types/town.types';
import { TownCards } from './TownCards';
import { TownLightbox, type TownTarget } from './TownLightbox';

// The scene (and three.js with it) is fetched only when this page shows it.
const TownScene = dynamic(() => import('./TownScene').then((m) => m.TownScene), { ssr: false });

/** WebGL present. Decided after mount (no SSR guess). Reduced motion still shows the town, static
 * (the scene itself skips the fly-in and parks everything). */
function useSceneAvailable(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let webgl = false;
    try {
      webgl = !!document.createElement('canvas').getContext('webgl2');
    } catch {
      webgl = false;
    }
    setAvailable(webgl);
  }, []);
  return available;
}

export function TownPage() {
  const [wallboard, setWallboard] = useState(false);
  const [target, setTarget] = useState<TownTarget | null>(null);
  const { snapshot, error, isLoading } = useTownSnapshot(wallboard ? { mode: 'wallboard' } : undefined);
  const sceneAvailable = useSceneAvailable();
  const ready = snapshot && !isPending(snapshot) ? snapshot : null;

  return (
    <div className="mx-auto w-full px-4 lg:px-6">
      <PageHeader
        title="Town"
        actions={
          <Button type="button" variant="primary" onClick={() => setWallboard((on) => !on)}>
            {wallboard ? 'Exit wallboard' : 'Wallboard'}
          </Button>
        }
      />
      {ready ? (
        <div className="mt-1 flex flex-wrap gap-2">
          <Badge variant="outline">As of {formatDateTimeInMalaysia(ready.as_of)}</Badge>
          {ready.data_as_of ? (
            <Badge variant="outline">Data as of {formatDateTimeInMalaysia(ready.data_as_of)}</Badge>
          ) : null}
        </div>
      ) : null}
      {error && !snapshot ? (
        <p className="mt-4 text-sm text-destructive">{error instanceof Error ? error.message : 'Failed to load the town'}</p>
      ) : null}
      {isLoading && !snapshot ? <SectionSkeleton rows={5} className="mt-4" label="Loading town" /> : null}
      {snapshot ? (
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 pb-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          {ready && sceneAvailable ? <TownScene snapshot={ready} onSelect={setTarget} /> : null}
          <div
            className={
              ready && sceneAvailable
                ? 'min-w-0 lg:max-h-[calc(100dvh-20rem)] lg:min-h-[22rem] lg:overflow-y-auto lg:overscroll-contain'
                : 'min-w-0 lg:col-span-2'
            }
          >
            <TownCards snapshot={snapshot} onOpen={setTarget} />
          </div>
        </div>
      ) : null}
      {snapshot ? <TownLightbox snapshot={snapshot} target={target} onClose={() => setTarget(null)} /> : null}
    </div>
  );
}
