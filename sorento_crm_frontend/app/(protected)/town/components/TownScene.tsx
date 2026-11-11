'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { WebGLRenderer } from 'three';
import { Map as MapIcon, Minus, Pause, Play, Plus, RotateCcw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { localStore } from '@/lib/storage';
import type { TownSnapshot } from '@/types/town.types';
import { DEFAULT_VIEW, type TownView } from '../lib/townCamera';
import { STATES, stateKeyOf } from '../lib/townMap';
import { newSales } from '../lib/townMotion';
import type { TownTarget } from './TownLightbox';
import { createTownRenderer, mountWorld, type TownTipState, type WorldHandle } from './townWorld';

export type { TownTipState } from './townWorld';

/**
 * The town in 3D (approved v6 look, TOWN-LOOK 10 Nov). The scene itself lives in `townWorld.ts`; this
 * shell owns the renderer, the camera view and the motion clock across snapshot polls, the tooltip,
 * the camera and motion buttons, and the sale beat: when a poll brings shops more invoices than the
 * last snapshot, the rebuilt town keeps its view (no second fly-in) and plays one beat.
 */

const HINT_KEY = 'town_hint_seen';
const HINT_MS = 6000;
const MOTION_KEY = 'town_motion';

const prefersReduced = () => {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  } catch {
    return false;
  }
};

const LEGEND = [
  ['bg-amber-500', 'Lit shop = bought today'],
  ['bg-slate-600', 'Glass tower = trading house'],
  ['bg-stone-400', 'Site = open project (its own dates)'],
  ['bg-teal-600', 'Flag = sales stage'],
  ['bg-red-600', 'Red = low stock, late, final negotiation'],
  ['bg-blue-600', 'Lorries = to deliver'],
  ['bg-violet-600', 'Violet = waiting approval'],
  ['bg-cyan-700', 'Ships = incoming, coaster = East Malaysia'],
] as const;

/** The state chips under the stage (TOWN-PROJECT-CITY): states with a dealer, site or trading house first. */
function statesByUse(snapshot: TownSnapshot) {
  const used = new Set(
    [...snapshot.shops.map((s) => s.state), ...(snapshot.projects?.sites ?? []).map((s) => s.state), ...(snapshot.trading_houses?.rows ?? []).map((r) => r.state)].map(stateKeyOf),
  );
  return STATES.map((s) => ({ key: s.key, name: s.name, used: used.has(s.key) })).sort((a, b) => Number(b.used) - Number(a.used));
}

export function TownScene({
  snapshot,
  mode,
  onSelect,
}: {
  snapshot: TownSnapshot;
  /** Which variant the snapshot is (`useTownSnapshot`'s mode): a change of view is never a sale. */
  mode?: 'wallboard';
  onSelect: (target: TownTarget) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const labelsRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<WorldHandle | null>(null);
  const engine = useRef<{
    renderer: WebGLRenderer | null;
    shown: TownSnapshot | null;
    mode: 'wallboard' | undefined;
    reduced: boolean | null;
    view: { current: TownView };
    clock: { current: number };
  }>({ renderer: null, shown: null, mode: undefined, reduced: null, view: { current: DEFAULT_VIEW }, clock: { current: 0 } });
  const [reduced, setReduced] = useState(prefersReduced);
  const [motion, setMotion] = useState(() => !reduced && localStore.getItem(MOTION_KEY) !== 'off');
  const motionRef = useRef(motion);

  // the viewer can turn reduced motion on or off while the town is open
  useEffect(() => {
    let query: MediaQueryList | undefined;
    try {
      query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    } catch {
      query = undefined;
    }
    if (!query?.addEventListener) return;
    const onChange = (event: MediaQueryListEvent) => {
      const on = !event.matches && localStore.getItem(MOTION_KEY) !== 'off';
      motionRef.current = on;
      setMotion(on);
      setReduced(event.matches);
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  const [tip, setTip] = useState<TownTipState | null>(null);
  const [tipLeft, setTipLeft] = useState(0);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const [hint, setHint] = useState(() => !localStore.getItem(HINT_KEY));

  const dismissHint = () => {
    setHint(false);
    localStore.setItem(HINT_KEY, '1');
  };

  useEffect(() => {
    if (!hint) return;
    const timer = window.setTimeout(dismissHint, HINT_MS);
    return () => window.clearTimeout(timer);
  }, [hint]);

  // the renderer outlives the snapshot rebuilds; it goes with the component
  useEffect(() => {
    const state = engine.current;
    return () => {
      state.renderer?.dispose();
      state.renderer = null;
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    const labelLayer = labelsRef.current;
    if (!canvas || !stage || !labelLayer) return;
    const state = engine.current;
    state.renderer ??= createTownRenderer(canvas);
    const prev = state.shown;
    // the first snapshot flies in; a remount of the same one (React strict mode) does too
    // a reduced-motion switch rebuilds the same snapshot: no fly-in for that
    const reducedSwitched = state.reduced !== null && state.reduced !== reduced;
    state.reduced = reduced;
    const intro = (!prev || prev === snapshot) && !reducedSwitched;
    // toggling the Wallboard swaps in the other variant (its own cache, its own shop keys): keep the
    // view, but start a new baseline, so the swap never plays as a sale
    const sameView = state.mode === mode;
    state.mode = mode;
    state.shown = snapshot;
    const world = mountWorld({
      canvas,
      stage,
      labelLayer,
      renderer: state.renderer,
      snapshot,
      prev: sameView ? prev : null,
      beat: intro || !sameView ? null : newSales(prev, snapshot),
      intro,
      reduced,
      motion: motionRef,
      view: state.view,
      clock: state.clock,
      select: (target) => {
        dismissHint();
        setTip(null);
        selectRef.current(target);
      },
      hover: setTip,
    });
    worldRef.current = world;
    return () => {
      worldRef.current = null;
      setTip(null);
      world.dispose();
    };
  }, [snapshot, reduced, mode]);

  // keep the tooltip inside the stage at 375 px
  useLayoutEffect(() => {
    if (!tip) return;
    const width = tipRef.current?.offsetWidth ?? 0;
    const stageWidth = stageRef.current?.clientWidth ?? 0;
    const half = width / 2 + 6;
    setTipLeft(stageWidth > 2 * half ? Math.min(Math.max(tip.x, half), stageWidth - half) : tip.x);
  }, [tip]);

  const toggleMotion = () => {
    const on = !motionRef.current;
    motionRef.current = on;
    setMotion(on);
    localStore.setItem(MOTION_KEY, on ? 'on' : 'off');
    worldRef.current?.setMotion(on);
  };

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-xl border border-border sm:h-[calc(100dvh-20rem)] sm:min-h-[22rem] sm:max-h-[41rem] ${
        snapshot.phase === 'night' ? 'bg-slate-800' : 'bg-sky-50 dark:bg-slate-800'
      }`}
    >
      <div ref={stageRef} className="relative isolate aspect-[3/4] min-h-[25rem] sm:aspect-auto sm:min-h-0 sm:flex-1">
        <canvas
          ref={canvasRef}
          aria-label="Town"
          className="absolute inset-0 block size-full cursor-grab touch-none opacity-0 transition-opacity duration-(--duration-slow) ease-(--ease-standard) data-[ready]:opacity-100"
        />
        <div ref={labelsRef} className="pointer-events-none absolute inset-0 z-[2] overflow-hidden" />
        {snapshot.phase === 'night' ? (
          <Badge variant="secondary" size="lg" className="absolute start-1/2 top-2.5 z-[3] -translate-x-1/2">
            Closed for the day
          </Badge>
        ) : null}
        {tip ? (
          <div
            ref={tipRef}
            role="tooltip"
            className="pointer-events-none absolute z-10 max-w-64 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md"
            style={{ left: tipLeft || tip.x, top: tip.y - 12 }}
          >
            <div className="truncate font-semibold">{tip.title}</div>
            <div className="truncate text-muted-foreground">{tip.detail}</div>
          </div>
        ) : null}
        <div className="absolute bottom-2 end-2 z-[3] flex gap-1 rounded-lg border border-border bg-background/80 p-1 backdrop-blur">
          <Button
            type="button"
            variant="ghost"
            mode="icon"
            size="sm"
            aria-label={motion ? 'Pause motion' : 'Play motion'}
            title={motion ? 'Pause motion' : 'Play motion'}
            onClick={toggleMotion}
          >
            {motion ? <Pause /> : <Play />}
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Zoom out" title="Zoom out" onClick={() => worldRef.current?.zoom(-1)}>
            <Minus />
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Zoom in" title="Zoom in" onClick={() => worldRef.current?.zoom(1)}>
            <Plus />
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Whole map" title="Whole map" onClick={() => worldRef.current?.flyTo('all')}>
            <MapIcon />
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Reset view" title="Reset view" onClick={() => worldRef.current?.reset()}>
            <RotateCcw />
          </Button>
        </div>
        {hint ? (
          <div className="pointer-events-none absolute start-1/2 top-3 z-[3] -translate-x-1/2 rounded-lg border border-border bg-background/80 px-3.5 py-2 text-sm font-semibold backdrop-blur">
            Tap any building
          </div>
        ) : null}
      </div>
      <div role="group" aria-label="Go to a state" className="flex gap-1.5 overflow-x-auto border-t border-border bg-background/80 px-3 py-2">
        {statesByUse(snapshot).map(({ key, name, used }) => (
          <button
            key={key}
            type="button"
            onClick={() => worldRef.current?.flyTo(key)}
            className={`shrink-0 rounded-full border border-border px-2.5 py-0.5 text-xs font-medium hover:bg-accent ${
              used ? 'bg-background text-foreground' : 'bg-transparent text-muted-foreground'
            }`}
          >
            {name}
          </button>
        ))}
      </div>
      <div
        role="group"
        className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border bg-background/80 px-3 py-2 text-xs sm:flex sm:flex-wrap"
        aria-label="Legend"
      >
        {LEGEND.map(([tone, text]) => (
          <div key={text} className="flex items-center gap-2">
            <span aria-hidden="true" className={`inline-block size-3 shrink-0 rounded-sm ${tone}`} />
            {text}
          </div>
        ))}
      </div>
    </div>
  );
}
