/**
 * M2-07 - exactly one TooltipProvider mounts app-wide, in
 * ClientProviders.tsx, with the calibrated 700ms-first/300ms-sibling
 * rhythm; `Tooltip` itself is a bare Root with no provider of its own.
 *
 * A second `<TooltipProvider>` anywhere below it would shadow the shared
 * delay for its own subtree - which is exactly the bug this slice fixes
 * (several toolbar buttons each mounted their own `delayDuration={300}` or
 * `{0}` provider, so the shared skipDelayDuration grouping never applied).
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';
import { render, screen } from '@testing-library/react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './tooltip';

const root = path.resolve(__dirname, '..', '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

/** Roots scanned for stray tooltip timing. */
const ROOTS = ['app', 'components'];

/**
 * Where a `delayDuration=` prop is legitimate:
 * - `components/ClientProviders.tsx` - the one app-wide provider (asserted above).
 * - `components/ui/tooltip.tsx` - the provider's own definition and forwarding.
 * - this file - it asserts on those two as source text.
 */
const TIMING_OWNERS = [
  'components/ClientProviders.tsx',
  'components/ui/tooltip.tsx',
  'components/ui/tooltip.provider.test.tsx',
];

/**
 * The one dense-toolbar carve-out named in DESIGN-LANGUAGE section 3: 15
 * unlabelled icons in a row make the label the affordance, so its Roots pass
 * `delayDuration={300}` - on the Root, which Radix reads per instance, NOT via
 * a second provider.
 */
const DENSE_TOOLBARS = [
  'app/(protected)/dealer-kit/tag-templates/components/CanvasToolbar.tsx',
];

/** Every `.ts`/`.tsx` under the scanned roots, this file included. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
      const rel = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(rel);
      } else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
        out.push(rel);
      }
    }
  };
  for (const dir of ROOTS) walk(dir);
  return out;
}

describe('Tooltip is a bare Root (M2-07)', () => {
  it('tooltip.tsx does not mount its own TooltipProvider inside Tooltip', () => {
    const source = read('components/ui/tooltip.tsx');
    const tooltipFn = source.slice(source.indexOf('function Tooltip('));
    // Only the exported TooltipProvider definition itself may mention the
    // name above this point; Tooltip's own body must not reference it.
    expect(tooltipFn.slice(0, tooltipFn.indexOf('function TooltipTrigger'))).not.toContain('<TooltipProvider');
  });

  it('ClientProviders.tsx mounts the one TooltipProvider with the calibrated delays', () => {
    const source = read('components/ClientProviders.tsx');
    const matches = source.match(/<TooltipProvider/g) ?? [];
    expect(matches).toHaveLength(1);
    expect(source).toContain('delayDuration={700}');
    expect(source).toContain('skipDelayDuration={300}');
  });

  /**
   * M2-07 fix round - the shared rhythm holds across the whole tree.
   *
   * The provider count above only speaks for ClientProviders.tsx. What actually
   * breaks the 700ms-first/300ms-sibling grouping is any OTHER file setting its
   * own tooltip timing, whether through a second provider or a per-Root
   * override - so this enumerates every `delayDuration=` in the source tree and
   * allows exactly one: the dense icon toolbar the design language names.
   */
  it('no file outside the named carve-out sets its own tooltip delay', () => {
    const offenders = sourceFiles().filter(
      (rel) => !TIMING_OWNERS.includes(rel) && read(rel).includes('delayDuration='),
    );

    expect(offenders.sort()).toEqual(DENSE_TOOLBARS);
  });

  /**
   * M2-07 fix round - a tooltip is instant in and out, and the code says so.
   *
   * The content used to carry `opacity-0 transition-opacity` plus
   * `data-[state=delayed-open]:opacity-100`, which never ran either way.
   * Radix mounts the content already carrying `delayed-open`/`instant-open`
   * (its `stateAttribute` is only `closed` while the content is unmounted), so
   * the entry has no starting value to travel from; and Radix's Presence waits
   * on `animationend` only, so a transition-only style unmounts on the closing
   * frame and the exit never runs either. A hover is a tens-of-times-a-day
   * interaction - the frequency gate allows none or a fast opacity - so the
   * pairing goes rather than the fade being resurrected with a keyframe.
   */
  it('renders no TooltipContent entry/exit animation at all (instant in and out)', () => {
    const source = read('components/ui/tooltip.tsx');
    expect(source).not.toContain('zoom-in-95');
    expect(source).not.toContain('animate-in');
    expect(source).not.toContain('transition-opacity');
    expect(source).not.toContain('opacity-0');
    expect(source).not.toContain('data-[state=delayed-open]');
  });

  // A behavioural "throws with no ancestor TooltipProvider" case is NOT
  // covered here: vitest.config.ts (not vitest.setup.ts - an alias has to run
  // before Vite resolves the import graph) points `@/components/ui/tooltip` at
  // test-mocks/ui-tooltip.tsx, which wraps Tooltip in the calibrated Provider,
  // so the ~60 unrelated tests that happen to render a page with a Tooltip in
  // it don't each need their own wrapper - which means Radix's real "must be
  // used within TooltipProvider" guard is deliberately not exercised in this
  // suite. This file imports './tooltip' by relative path, so it reads the
  // real module; the source checks above are what prove tooltip.tsx ships no
  // self-wrapping.

  it('works once wrapped in the shared TooltipProvider', () => {
    render(
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger>Trigger</TooltipTrigger>
          <TooltipContent>Tip</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    expect(screen.getAllByText('Tip').length).toBeGreaterThan(0);
  });
});
