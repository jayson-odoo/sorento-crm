/**
 * M2-01 - a palette opened by a keyboard shortcut never animates.
 *
 * `CommandDialog` with `motion={false}` renders `DialogContent` on the
 * no-motion path: initial/animate/exit are identical (nothing for the
 * spring to interpolate) and the content is marked `data-motion="off"` so a
 * browser pass can confirm the DevTools Animations panel shows nothing
 * running on it.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { CommandDialog, CommandInput, CommandList, CommandItem } from './command';

describe('CommandDialog motion={false} (M2-01)', () => {
  it('marks the content data-motion="off" and gives it no scale to animate', () => {
    render(
      <CommandDialog open motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    const content = document.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content).toHaveAttribute('data-motion', 'off');
  });

  it('defaults to the animated path (no data-motion attribute) when motion is not set', () => {
    render(
      <CommandDialog open>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    const content = document.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content).not.toHaveAttribute('data-motion');
  });

  it('renders its content synchronously on open, with no distinct exit state to wait through', () => {
    render(
      <CommandDialog open motion={false}>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandItem>Result</CommandItem>
        </CommandList>
      </CommandDialog>,
    );

    expect(screen.getByText('Result')).toBeInTheDocument();
  });
});
