/**
 * S8-02 - the scale animates from the trigger, not from dead centre.
 *
 * `PopoverContent` and `DropdownMenuContent` split into a static outer node (Radix's
 * own Popper positioning transform lives there) and an inner `motion.div` that Framer
 * Motion actually scales/fades (see the S8-01/S8-02 comment in each file). Radix sets
 * a PER-PRIMITIVE transform-origin variable - `--radix-popover-content-transform-origin`,
 * `--radix-dropdown-menu-content-transform-origin` - as an inline style on the outer
 * node, not the generic `--radix-popper-content-transform-origin` (which Radix never
 * sets, so it silently resolved to the CSS-initial 50%/50%, dead centre). The origin
 * class has to both (a) name the primitive's own variable and (b) sit on the INNER
 * node that actually scales - a CSS custom property inherits down to it from the
 * outer node, but a class on the wrong element never anchors anything.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { Popover, PopoverContent, PopoverTrigger } from './popover';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './dropdown-menu';

describe('Popover anchors its scale to the trigger side (S8-02)', () => {
  it('puts the popover primitive origin on the inner animated node, not the outer wrapper', async () => {
    render(
      <Popover>
        <PopoverTrigger>Open popover</PopoverTrigger>
        <PopoverContent>Popover body</PopoverContent>
      </Popover>,
    );

    fireEvent.click(screen.getByText('Open popover'));
    const body = await screen.findByText('Popover body');

    const outer = document.querySelector('[data-slot="popover-content"]');
    expect(outer).not.toBeNull();
    expect(outer?.className ?? '').not.toContain('transform-origin');

    const inner = body.closest('div');
    expect(inner).not.toBeNull();
    expect(inner?.className).toContain('origin-(--radix-popover-content-transform-origin)');
    // Never the generic, non-existent Radix variable this bug used to reference.
    expect(inner?.className).not.toContain('--radix-popper-content-transform-origin');
  });
});

describe('DropdownMenu anchors its scale to the trigger side (S8-02)', () => {
  it('puts the dropdown-menu primitive origin on the inner animated node, not the outer wrapper', async () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Item one</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    fireEvent.pointerDown(screen.getByRole('button', { name: 'Open menu' }), { button: 0 });
    const item = await screen.findByText('Item one');

    const outer = document.querySelector('[data-slot="dropdown-menu-content"]');
    expect(outer).not.toBeNull();
    expect(outer?.className ?? '').not.toContain('transform-origin');

    const inner = item.closest('[class*="min-w-[8rem]"]');
    expect(inner).not.toBeNull();
    expect(inner?.className).toContain('origin-(--radix-dropdown-menu-content-transform-origin)');
    expect(inner?.className).not.toContain('--radix-popper-content-transform-origin');
  });
});
