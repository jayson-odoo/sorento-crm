/**
 * QUOTE-COVER-DESIGN B1: the drag overlay copy of a row must render under document.body, not
 * inside the Radix dialog (a transformed ancestor offsets a position:fixed overlay).
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';

const ROWS = ['alpha', 'beta', 'gamma'];

function Harness() {
  const [rows, setRows] = React.useState(ROWS);
  return (
    <Dialog open>
      <DialogContent>
        <DialogTitle>Rows</DialogTitle>
        <Sortable value={rows} onValueChange={setRows} getItemValue={(r) => r} strategy="vertical">
          {rows.map((row) => (
            <SortableItem key={row} value={row} asChild>
              <div role="group" aria-label={row}>
                <SortableItemHandle asChild>
                  <button type="button" aria-label={`Drag ${row} to reorder`}>
                    grip
                  </button>
                </SortableItemHandle>
              </div>
            </SortableItem>
          ))}
        </Sortable>
      </DialogContent>
    </Dialog>
  );
}

describe('Sortable drag overlay inside a dialog (B1)', () => {
  it('renders the overlay copy of the dragged row outside the dialog, under document.body', async () => {
    render(<Harness />);
    const handle = screen.getByRole('button', { name: 'Drag beta to reorder' });
    handle.focus();
    fireEvent.keyDown(handle, { key: ' ', code: 'Space' });
    await new Promise((r) => setTimeout(r, 50));

    // The drag started: the dragged row now exists twice (original + overlay clone).
    const copies = await screen.findAllByLabelText('Drag beta to reorder');
    expect(copies).toHaveLength(2);
    const original = copies.find((c) => c.closest('[data-slot="sortable"]'))!;
    const overlay = copies.find((c) => !c.closest('[data-slot="sortable"]'))!;
    expect(original).toBeTruthy();
    expect(overlay).toBeTruthy();

    expect(original.closest('[role="dialog"]')).not.toBeNull();
    expect(overlay.closest('[role="dialog"]')).toBeNull();
    expect(document.body.contains(overlay)).toBe(true);
  });
});
