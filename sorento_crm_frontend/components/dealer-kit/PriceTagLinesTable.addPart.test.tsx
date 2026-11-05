/**
 * P2 / P3 on the lines table: Add part lists the combo's own missing rows first, and the package
 * warning shares one block with the line's red messages.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

type Opt = { value: string; label: string; group?: string };

// Async stand-in: asks for the options the way the real select does and lists them by group.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    options?: Opt[];
    fetchOptions?: (q: string, page: number) => Promise<Opt[]>;
    onOptionChange?: (o: Opt | null) => void;
  }) => {
    const [loaded, setLoaded] = React.useState<Opt[]>([]);
    React.useEffect(() => {
      if (props.fetchOptions) void props.fetchOptions('', 0).then(setLoaded);
    }, [props.fetchOptions]);
    const all = props.options ?? loaded;
    return (
      <ul aria-label={props.placeholder ?? ''}>
        {all.map((o) => (
          <li key={o.value}>
            <button type="button" data-group={o.group ?? ''} onClick={() => props.onOptionChange?.(o)}>
              {o.label}
            </button>
          </li>
        ))}
      </ul>
    );
  },
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({ SearchableMultiSelect: () => null }));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { emptyDraftLine, partsFromCombo, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

const combo = {
  combo_id: 'c1',
  name: 'Sink combo',
  parts: [
    { product_id: 'fx', code: 'SRTFIX', name: 'Fixed', choice_group: null },
    { product_id: 'ta', code: 'SRTKT1', name: 'Tap A', choice_group: 'Kitchen tap' },
    { product_id: 'tb', code: 'SRTKT2', name: 'Tap B', choice_group: 'Kitchen tap' },
    { product_id: 'up', code: 'SRTKT71SS', name: 'Upgrade', choice_group: null, is_upgrade: true },
  ],
} as never;

function renderTable(keep: (role: string | null) => boolean, patch: Record<string, unknown> = {}) {
  const restorePart = vi.fn();
  const addPart = vi.fn();
  const editor = new Proxy(
    {
      linePricing: {},
      restorePart,
      addPart,
      fetchItemOptions: async () => [],
      fetchPartOptions: async () => [{ value: 'product:zz', label: 'ZZ extra' }],
    },
    { get: (target, key) => (key in target ? (target as never)[key] : vi.fn()) },
  ) as never;
  const line = {
    ...emptyDraftLine(),
    key: 'l1',
    product_id: 'host',
    code: 'HOST',
    name: 'Host',
    combo_id: 'c1',
    combos: [combo],
    combos_loaded: true,
    host_guarded: true,
    tag_templates_for: 'host',
    tag_templates_combo: 'c1',
    tag_templates: [{ id: 't', name: 'T', family: 'x', published: true, width_mm: 1, height_mm: 1, needs: { fixed: 1, groups: [2], upgrades: 1 } }],
    tag_template_id: 't',
    parts: partsFromCombo(combo).filter((p) => keep(p.role)),
    ...patch,
  } as unknown as DraftLine;
  render(<PriceTagLinesTable lines={[line]} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />);
  return { restorePart, addPart };
}

describe('P2: Add part lists the combo rows first', () => {
  it('offers the deleted Upgrade row alone, under "This package", then the catalogue', async () => {
    const { restorePart, addPart } = renderTable((role) => role !== 'Upgrade');
    const add = screen.getByLabelText('Add part');
    await waitFor(() => expect(add.querySelectorAll('button').length).toBe(2));
    const buttons = Array.from(add.querySelectorAll('button'));
    expect(buttons.map((b) => b.textContent)).toEqual(['Upgrade', 'ZZ extra']);
    expect(buttons[0].dataset.group).toBe('This package');

    fireEvent.click(buttons[0]);
    expect(restorePart).toHaveBeenCalledWith('l1', 'role:Upgrade');
    expect(addPart).not.toHaveBeenCalled();

    fireEvent.click(buttons[1]);
    expect(addPart).toHaveBeenCalledTimes(1);
  });

  it('lists only the catalogue while the line holds every combo row', async () => {
    renderTable(() => true);
    const add = screen.getByLabelText('Add part');
    await waitFor(() => expect(add.querySelectorAll('button').length).toBe(1));
    expect(add.textContent).toBe('ZZ extra');
  });
});

describe('P3: the package warning sits in the line message block', () => {
  it('shows the warning and a red error in ONE block, each in its own style', () => {
    renderTable((role) => role !== 'Upgrade' && role !== 'Kitchen tap', {
      guard_error: 'No combo list price.',
    });
    const warning = screen.getByText('Package warning');
    const error = screen.getByText('No combo list price.');
    expect(warning.closest('tr')).toBe(error.closest('tr'));
    expect(error.className).toContain('text-destructive');
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument();
  });

  it('shows the warning alone, as a warning, when there is no error', () => {
    renderTable((role) => role !== 'Kitchen tap');
    expect(screen.getByText('Package warning')).toBeInTheDocument();
    expect(document.querySelector('[data-error-anchor]')).toBeNull();
  });
});
