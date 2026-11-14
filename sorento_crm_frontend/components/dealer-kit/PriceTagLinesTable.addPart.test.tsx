/**
 * P3 on the lines table: the package warning shares one block with the line's red messages.
 * (P2, Add part's own combo rows, went with Add part itself: owner 13 Nov, PRICETAG-ALA-CARTE AC-18.)
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
  const editor = new Proxy(
    {
      linePricing: {},
      fetchItemOptions: async () => [],
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
}

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
