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

  it('renders no TooltipContent zoom class (opacity only)', () => {
    const source = read('components/ui/tooltip.tsx');
    expect(source).not.toContain('zoom-in-95');
    expect(source).not.toContain('animate-in');
  });

  // A behavioural "throws with no ancestor TooltipProvider" case is NOT
  // covered here: vitest.setup.ts globally shims @radix-ui/react-tooltip's
  // Root so the ~60 unrelated tests that happen to render a page with a
  // Tooltip in it don't each need their own wrapper (see that file's
  // comment) - which means Radix's real "must be used within
  // TooltipProvider" guard is deliberately not exercised in this suite. The
  // source check above is what actually proves tooltip.tsx ships no
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
