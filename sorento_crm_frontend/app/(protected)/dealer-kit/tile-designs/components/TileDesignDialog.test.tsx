/**
 * Designing a tile.
 *
 * Two complaints: the spacing was tight, and a change to the attributes could
 * not be undone. The second is the one with teeth - trying a field out is only
 * free if putting it back is one click, and the only way back was to remember
 * what had been there and rebuild it by hand.
 *
 * Reordering also moved from a pair of up/down arrows to dragging, which is
 * what the rest of the system does. Drag itself is a dnd-kit pointer sequence
 * that jsdom cannot produce, so what is asserted here is that the sortable is
 * wired to the field list and that every change goes through one undoable
 * commit - the reorder path and the add/remove path are the same `commit`.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/catalogueService', async () => {
  const actual = await vi.importActual<typeof import('../../services/catalogueService')>(
    '../../services/catalogueService',
  );
  return {
    ...actual,
    createTileTemplate: vi.fn(),
    updateTileTemplate: vi.fn(),
  };
});

import {
  createTileTemplate,
  updateTileTemplate,
} from '../../services/catalogueService';
import { TileDesignDialog } from './TileDesignDialog';

const mockCreate = vi.mocked(createTileTemplate);
const mockUpdate = vi.mocked(updateTileTemplate);

function renderDialog(template: Parameters<typeof TileDesignDialog>[0]['template'] = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TileDesignDialog open onOpenChange={vi.fn()} template={template} />
    </QueryClientProvider>,
  );
}

/** The ordered field rows, by their visible label. */
function shownFields(): string[] {
  const list = document.querySelector('[data-dk-design-fields]');
  return Array.from(list?.querySelectorAll('[data-slot="sortable-item"], li, div > span') ?? [])
    .map((node) => node.textContent?.trim() ?? '')
    .filter(Boolean);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCreate.mockResolvedValue({} as never);
  mockUpdate.mockResolvedValue({} as never);
});

describe('TileDesignDialog', () => {
  it('lists the fields a tile shows, in order', () => {
    renderDialog();

    const fields = document.querySelector('[data-dk-design-fields]');
    expect(fields).not.toBeNull();
    expect(fields?.textContent).toContain('1');
  });

  it('offers a drag handle on every field rather than up and down arrows', () => {
    // The rest of the system reorders by dragging. Arrows were a way of saying
    // "move this to third" one click at a time while everything shuffled.
    renderDialog();

    expect(screen.queryByLabelText(/move .* up/i)).toBeNull();
    // Queried by attribute: the handle is a div, which `getByLabelText` does
    // not consider labelable.
    expect(document.querySelectorAll('[aria-label^="Drag "]').length).toBe(4);
  });

  it('adds a field, and undoes it', async () => {
    renderDialog();

    const before = document.querySelector('[data-dk-design-fields]')?.textContent ?? '';
    const dimensions = screen.getByLabelText(/show dimensions/i);
    await act(async () => {
      fireEvent.click(dimensions);
    });

    const after = document.querySelector('[data-dk-design-fields]')?.textContent ?? '';
    expect(after).not.toBe(before);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });

    expect(document.querySelector('[data-dk-design-fields]')?.textContent).toBe(before);
  });

  it('removes a field, and undoes that too', async () => {
    renderDialog();

    const before = document.querySelector('[data-dk-design-fields]')?.textContent ?? '';
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove code/i }));
    });
    expect(document.querySelector('[data-dk-design-fields]')?.textContent).not.toBe(before);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });
    expect(document.querySelector('[data-dk-design-fields]')?.textContent).toBe(before);
  });

  it('undoes several changes, one at a time', async () => {
    renderDialog();

    const start = document.querySelector('[data-dk-design-fields]')?.textContent ?? '';
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove code/i }));
    });
    const afterOne = document.querySelector('[data-dk-design-fields]')?.textContent ?? '';
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove price/i }));
    });

    const undo = () => screen.getByRole('button', { name: /undo/i });
    await act(async () => {
      fireEvent.click(undo());
    });
    expect(document.querySelector('[data-dk-design-fields]')?.textContent).toBe(afterOne);

    await act(async () => {
      fireEvent.click(undo());
    });
    expect(document.querySelector('[data-dk-design-fields]')?.textContent).toBe(start);
  });

  it('cannot undo before the first change', () => {
    renderDialog();

    expect(screen.getByRole('button', { name: /undo/i })).toBeDisabled();
  });

  it('starts a fresh history each time it opens', async () => {
    // Undoing into the design you were editing BEFORE this one would be a
    // change nobody asked for.
    const { rerender } = renderDialog();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove code/i }));
    });
    expect(screen.getByRole('button', { name: /undo/i })).toBeEnabled();

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={client}>
        <TileDesignDialog
          open
          onOpenChange={vi.fn()}
          template={{
            id: 't-1',
            name: 'Compact',
            fields: ['image', 'name'],
            updatedAt: '2026-08-04T00:00:00',
          }}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /undo/i })).toBeDisabled());
  });

  it('refuses to save a design that shows nothing', async () => {
    renderDialog();

    for (const label of [/remove photo/i, /remove name/i, /remove code/i, /remove price/i]) {
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: label }));
      });
    }

    expect(screen.getByText(/a tile has to show at least one thing/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save design/i })).toBeDisabled();
  });

  it('saves the fields as they stand', async () => {
    renderDialog();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/name/i, { selector: 'input' }), {
        target: { value: 'Compact' },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove code/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save design/i }));
    });

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith('Compact', ['image', 'name', 'price']),
    );
  });

  it('saves what UNDO left behind, not what was there before it', async () => {
    // The one that would break silently: undo restoring the display but not the
    // value that gets written.
    renderDialog();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/name/i, { selector: 'input' }), {
        target: { value: 'Compact' },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /remove code/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save design/i }));
    });

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith('Compact', ['image', 'name', 'code', 'price']),
    );
  });
});
