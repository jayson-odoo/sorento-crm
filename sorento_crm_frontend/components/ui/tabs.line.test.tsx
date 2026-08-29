/**
 * S1-04 - underline tabs everywhere, and a strip that scrolls.
 *
 * `tabs.tsx` defaulted to the pill variant and had no scroller, so Settings hid
 * 7 of its 10 tabs at 375 and the Product create strip overlapped five pills.
 * The default is now the line variant, which is the one every detail view and
 * form already reaches for, and the list owns its own horizontal scroller so a
 * long strip never widens the page.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs';

function Harness({ variant }: { variant?: 'default' | 'button' | 'line' }) {
  return (
    <Tabs defaultValue="a">
      <TabsList variant={variant} data-testid="list">
        <TabsTrigger value="a">Overview</TabsTrigger>
        <TabsTrigger value="b">History</TabsTrigger>
      </TabsList>
      <TabsContent value="a">A</TabsContent>
    </Tabs>
  );
}

describe('Tabs (S1-04)', () => {
  it('S1-04: a TabsList with no variant renders the line variant', () => {
    render(<Harness />);

    const list = screen.getByTestId('list');
    expect(list).toHaveClass('border-b');
    expect(list).not.toHaveClass('bg-accent');

    // ...and its triggers are underlines, not pills.
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveClass('border-b-2');
  });

  it('S1-04: the two-option segmented switches keep pills with an explicit variant', () => {
    render(<Harness variant="default" />);

    const list = screen.getByTestId('list');
    expect(list).toHaveClass('bg-accent');
    expect(screen.getByRole('tab', { name: 'Overview' })).not.toHaveClass('border-b-2');
  });

  it('S1-04: the list scrolls sideways with no visible scrollbar', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');

    expect(list).toHaveClass('overflow-x-auto');
    expect(list).toHaveClass('max-w-full');
    expect(list).toHaveClass('min-w-0');
    // The strip scrolls; the page does not.
    expect(list.className).toContain('[scrollbar-width:none]');
    expect(list.className).toContain('[&::-webkit-scrollbar]:hidden');
  });

  it('S1-04: the strip is masked at its right edge only while it scrolls', () => {
    render(<Harness />);
    const list = screen.getByTestId('list');

    // jsdom has no layout, so the strip "fits" and carries no mask.
    expect(list).toHaveAttribute('data-fade', 'false');
    expect(list.className).toContain(
      'data-[fade=true]:[mask-image:linear-gradient(to_right,black_calc(100%-24px),transparent)]',
    );
  });
});
