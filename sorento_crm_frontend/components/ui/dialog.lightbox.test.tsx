/**
 * S1-01, S1-02, S1-03 - every popup is a lightbox.
 *
 * `dialog.tsx` used to default `modal={false}` so the AI assistant bubble stayed
 * scrollable behind an open dialog. The cost was that 289 of 290 dialogs had no
 * focus trap and no scroll lock: the page behind stayed tabbable and a stray
 * wheel scrolled the list under the form. Radix inerts the bubble along with
 * everything else, which is the correct behaviour for a modal surface, so the
 * default flips and the bubble exemption goes.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { Dialog, DialogContent, DialogTitle, DialogTrigger } from './dialog';
import { AlertDialog, AlertDialogContent, AlertDialogTitle } from './alert-dialog';
import { Sheet, SheetBody, SheetContent, SheetTitle } from './sheet';

function DialogHarness() {
  return (
    <div>
      <p data-testid="behind">Behind the dialog</p>
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Edit record</DialogTitle>
          <button type="button">Inside</button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

describe('Dialog is a lightbox (S1-01)', () => {
  it('S1-01: with no explicit modal prop, the page behind is hidden from assistive tech', async () => {
    render(<DialogHarness />);

    fireEvent.click(screen.getByText('Open'));
    await screen.findByText('Edit record');

    // Radix only inerts the rest of the tree in modal mode.
    await waitFor(() => {
      expect(screen.getByTestId('behind').closest('[aria-hidden="true"]')).not.toBeNull();
    });
  });

  it('S1-01: Escape closes it and focus returns to the trigger', async () => {
    render(<DialogHarness />);

    const trigger = screen.getByText('Open');
    fireEvent.click(trigger);
    await screen.findByText('Edit record');

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape', code: 'Escape' });

    await waitFor(() => expect(screen.queryByText('Edit record')).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});

/**
 * Almost every dialog in this product is opened by a plain button flipping
 * state - 244 files render <Dialog>, 6 use <DialogTrigger> - so Radix has no
 * trigger node to hand focus back to and drops it on <body>. After Escape the
 * keyboard user is at the top of the document, having lost their place in the
 * list they were working.
 */
function StateOpenedHarness({ onCloseAutoFocus }: { onCloseAutoFocus?: (e: Event) => void }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Create Category
      </button>
      {/* A second way in, so a test can prove the SECOND open is restored to the
          button that opened it and not to the one before it. */}
      <button type="button" onClick={() => setOpen(true)}>
        Create Category from copy
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onCloseAutoFocus={onCloseAutoFocus}>
          <DialogTitle>Create Category</DialogTitle>
          <button type="button" onClick={() => setOpen(false)}>
            Cancel
          </button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

describe('Focus comes back to where it left (S1-01)', () => {
  it('S1-01: Escape returns focus to the plain button that opened it', async () => {
    render(<StateOpenedHarness />);

    const opener = screen.getByRole('button', { name: 'Create Category' });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByRole('button', { name: 'Cancel' });

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape', code: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it('S1-01: Cancel returns focus to the plain button that opened it', async () => {
    render(<StateOpenedHarness />);

    const opener = screen.getByRole('button', { name: 'Create Category' });
    opener.focus();
    fireEvent.click(opener);

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it('S1-01: a caller that wants focus somewhere else still wins, and does not poison the next open', async () => {
    // Takes over the FIRST close only. The second open then proves the opener
    // from the first was not still being held: if it were, the capture guard
    // would skip the new one and focus would go back to the wrong button.
    let takeOver = true;
    const onCloseAutoFocus = vi.fn((event: Event) => {
      if (takeOver) event.preventDefault();
    });
    render(<StateOpenedHarness onCloseAutoFocus={onCloseAutoFocus} />);

    const first = screen.getByRole('button', { name: 'Create Category' });
    first.focus();
    fireEvent.click(first);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(onCloseAutoFocus).toHaveBeenCalled());
    await waitFor(() => expect(document.activeElement).toBe(document.body));

    takeOver = false;
    const second = screen.getByRole('button', { name: 'Create Category from copy' });
    second.focus();
    fireEvent.click(second);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(document.activeElement).toBe(second));
  });
});

describe('Overlay is one shared scrim (S1-02)', () => {
  const surfaces: Array<[string, () => React.ReactElement, string]> = [
    [
      'dialog',
      () => (
        <Dialog open>
          <DialogContent>
            <DialogTitle>D</DialogTitle>
          </DialogContent>
        </Dialog>
      ),
      '[data-slot="dialog-overlay"]',
    ],
    [
      'alert dialog',
      () => (
        <AlertDialog open>
          <AlertDialogContent>
            <AlertDialogTitle>A</AlertDialogTitle>
          </AlertDialogContent>
        </AlertDialog>
      ),
      '[data-slot="alert-dialog-overlay"]',
    ],
    [
      'sheet',
      () => (
        <Sheet open>
          <SheetContent>
            <SheetTitle>S</SheetTitle>
          </SheetContent>
        </Sheet>
      ),
      '[data-slot="sheet-overlay"]',
    ],
  ];

  for (const [name, renderSurface, selector] of surfaces) {
    it(`S1-02: the ${name} scrim is 50% black with an 8px blur`, () => {
      render(renderSurface());
      const overlay = document.querySelector(selector);

      expect(overlay).not.toBeNull();
      expect(overlay).toHaveClass('bg-black/50');
      expect(overlay).toHaveClass('backdrop-blur-md');
      // The blur fades in with the scrim rather than snapping on.
      expect(overlay).toHaveClass('data-[state=open]:animate-in');
    });

    it(`S1-02: the ${name} scrim drops the blur under reduced transparency`, () => {
      render(renderSurface());
      const className = document.querySelector(selector)!.getAttribute('class') ?? '';

      expect(className).toContain('[@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none');
      expect(className).toContain('[@media(prefers-reduced-transparency:reduce)]:bg-black/72');
    });
  }
});

describe('Tall surfaces stay reachable (S1-03)', () => {
  it('S1-03: an alert dialog caps its height and scrolls', () => {
    render(
      <AlertDialog open>
        <AlertDialogContent>
          <AlertDialogTitle>Confirm</AlertDialogTitle>
        </AlertDialogContent>
      </AlertDialog>,
    );
    const content = document.querySelector('[data-slot="alert-dialog-content"]');

    expect(content).toHaveClass('max-h-[90dvh]');
    expect(content).toHaveClass('overflow-y-auto');
  });

  it('S1-03: a sheet body scrolls so the footer stays on screen', () => {
    render(
      <Sheet open>
        <SheetContent>
          <SheetTitle>S</SheetTitle>
          <SheetBody>tall</SheetBody>
        </SheetContent>
      </Sheet>,
    );

    const content = document.querySelector('[data-slot="sheet-content"]');
    expect(content).not.toBeNull();

    const body = document.querySelector('[data-slot="sheet-body"]');
    expect(body).toHaveClass('flex-1');
    expect(body).toHaveClass('min-h-0');
    expect(body).toHaveClass('overflow-y-auto');
  });

  it('S1-03: a top or bottom sheet caps its height', () => {
    render(
      <Sheet open>
        <SheetContent side="bottom">
          <SheetTitle>S</SheetTitle>
        </SheetContent>
      </Sheet>,
    );

    expect(document.querySelector('[data-slot="sheet-content"]')).toHaveClass('max-h-[90dvh]');
  });

  it('S1-03: a passive utility sheet can opt out of the scrim', () => {
    render(
      <Sheet open>
        <SheetContent overlay={false}>
          <SheetTitle>S</SheetTitle>
        </SheetContent>
      </Sheet>,
    );

    expect(document.querySelector('[data-slot="sheet-overlay"]')).toBeNull();
  });

  it('S1-03: dropping the scrim is not enough - a passive panel is also not modal', () => {
    render(
      <div>
        <p data-testid="behind">Behind the panel</p>
        <Sheet open modal={false}>
          <SheetContent overlay={false}>
            <SheetTitle>S</SheetTitle>
          </SheetContent>
        </Sheet>
      </div>,
    );

    // `overlay={false}` only removes the paint. Radix still locks and inerts the
    // page unless the ROOT says modal={false}, which left the three utility
    // panels dimming nothing while nothing behind them answered.
    expect(screen.getByTestId('behind').closest('[aria-hidden="true"]')).toBeNull();
  });

  it('S1-03: a modal sheet still inerts the page, so the two props are independent', async () => {
    render(
      <div>
        <p data-testid="behind">Behind the panel</p>
        <Sheet open>
          <SheetContent overlay={false}>
            <SheetTitle>S</SheetTitle>
          </SheetContent>
        </Sheet>
      </div>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('behind').closest('[aria-hidden="true"]')).not.toBeNull();
    });
  });
});
