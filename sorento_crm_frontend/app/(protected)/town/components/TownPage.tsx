'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/PageHeader';
import { useTownSnapshot } from '@/hooks/useTownSnapshot';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { isPending } from '@/types/town.types';
import { TownCards } from './TownCards';
import { TownPanel, type TownTarget } from './TownPanel';

// The scene (and three.js with it) is fetched only when this page shows it.
const TownScene = dynamic(() => import('./TownScene').then((m) => m.TownScene), { ssr: false });

/** WebGL present and the user not asking for reduced motion. Decided after mount (no SSR guess). */
function useSceneAvailable(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    let webgl = false;
    try {
      webgl = !!document.createElement('canvas').getContext('webgl2');
    } catch {
      webgl = false;
    }
    setAvailable(webgl && !reduced);
  }, []);
  return available;
}

export function TownPage() {
  const [wallboard, setWallboard] = useState(false);
  const [target, setTarget] = useState<TownTarget | null>(null);
  const { snapshot, error } = useTownSnapshot(wallboard ? { mode: 'wallboard' } : undefined);
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
      {snapshot ? (
        <div className="mt-4 grid gap-4 pb-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          {ready && sceneAvailable ? <TownScene snapshot={ready} onSelect={setTarget} /> : null}
          <div className={ready && sceneAvailable ? '' : 'lg:col-span-2'}>
            <TownCards snapshot={snapshot} onOpen={setTarget} />
          </div>
        </div>
      ) : null}
      {snapshot ? <TownPanel snapshot={snapshot} target={target} onClose={() => setTarget(null)} /> : null}
    </div>
  );
}
