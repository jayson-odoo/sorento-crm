/**
 * UI v2 phase 0, slice S4 (red first). UAC E-5 (decision D7, playbook P7 "side panels on phones").
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   components/v2/Lightbox.tsx : Lightbox(props)
 *     props: {
 *       open: boolean;
 *       onOpenChange: (open: boolean) => void;
 *       title: string;                 // the accessible name of the surface, always rendered as visible text
 *       children: ReactNode;           // the body
 *       footer?: ReactNode;            // action buttons, rendered after the body
 *     }
 *   Viewport rule (one breakpoint, 720 px, read from window.matchMedia with a `max-width`/`min-width` query
 *   or from window.innerWidth; the tests set both consistently):
 *     width > 720   : a centred Dialog   -> content element has data-slot="dialog-content"
 *     width <= 720  : a vaul bottom Drawer -> content element has data-slot="drawer-content"
 *   Both variants take the same props and show title, body and footer. Closed (open=false) renders neither.
 *   Lightbox.tsx never imports `@/components/ui/sheet` (D7: no side Sheet in v2 code).
 */
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { Lightbox } from './Lightbox';

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => {
      const max = /max-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const min = /min-width:\s*(\d+(?:\.\d+)?)px/.exec(query);
      const matches = max || min ? (max ? width <= Number(max[1]) : true) && (min ? width >= Number(min[1]) : true) : false;
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    },
  });
}

function renderLightbox(over: Partial<React.ComponentProps<typeof Lightbox>> = {}) {
  const onOpenChange = vi.fn();
  const onSave = vi.fn();
  render(
    <Lightbox
      open
      onOpenChange={onOpenChange}
      title="Order history"
      footer={<button type="button" onClick={onSave}>Save changes</button>}
      {...over}
    >
      <p>Line 1 was reserved</p>
    </Lightbox>,
  );
  return { onOpenChange, onSave };
}

beforeEach(() => setViewport(1280));
afterEach(cleanup);

describe('Lightbox (E-5)', () => {
  it('above 720 px renders a centred Dialog with title, body and footer', () => {
    renderLightbox();
    expect(document.querySelector('[data-slot="dialog-content"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="drawer-content"]')).toBeNull();
    expect(screen.getByText('Order history')).toBeInTheDocument();
    expect(screen.getByText('Line 1 was reserved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
  });

  it('at 721 px it is still the Dialog', () => {
    setViewport(721);
    renderLightbox();
    expect(document.querySelector('[data-slot="dialog-content"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="drawer-content"]')).toBeNull();
  });

  it('at 720 px and below renders a bottom Drawer with the same title, body and footer', () => {
    setViewport(720);
    renderLightbox();
    expect(document.querySelector('[data-slot="drawer-content"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="dialog-content"]')).toBeNull();
    expect(screen.getByText('Order history')).toBeInTheDocument();
    expect(screen.getByText('Line 1 was reserved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
  });

  it('a footer action runs its own handler in both variants', () => {
    for (const width of [1280, 360]) {
      setViewport(width);
      const { onSave } = renderLightbox();
      fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
      expect(onSave).toHaveBeenCalledTimes(1);
      cleanup();
    }
  });

  it('closed (open=false) renders neither variant', () => {
    for (const width of [1280, 360]) {
      setViewport(width);
      renderLightbox({ open: false });
      expect(document.querySelector('[data-slot="dialog-content"]')).toBeNull();
      expect(document.querySelector('[data-slot="drawer-content"]')).toBeNull();
      expect(screen.queryByText('Order history')).toBeNull();
      cleanup();
    }
  });

  it('Escape asks the parent to close it (Dialog)', () => {
    const { onOpenChange } = renderLightbox();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('never imports the side Sheet (D7)', () => {
    const src = fs.readFileSync(path.resolve(__dirname, 'Lightbox.tsx'), 'utf8');
    expect(src).not.toMatch(/components\/ui\/sheet['"]/);
    expect(src).not.toMatch(/SheetContent/);
  });
});
