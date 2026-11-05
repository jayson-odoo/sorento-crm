/**
 * PRICETAG-COMBO-RENDER K6 / AC-B3: the combo's template picker shows each template's needs in
 * the combo's own words and lists one that does not fit as a disabled option with the reason.
 *
 * Written test-FIRST. `parts` is not a prop yet and the options carry no needs text.
 * Decision: option description with `parts` = `<w> x <h> mm. <needsText>` (fits) or the
 * `fitReason` alone (does not fit), with `disabled: true` and `badgeText: 'Does not fit'`.
 * Without `parts` the option is exactly what it is today.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';

const templates = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  usePriceTagTemplateOptions: () => ({ data: templates(), error: null, refetch: vi.fn() }),
}));

type Opt = { value: string; label: string; description?: string; disabled?: boolean; badgeText?: string };
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ options = [] }: { options?: Opt[] }) => (
    <ul>
      {options.map((o) => (
        <li
          key={o.value}
          data-testid={`opt-${o.value}`}
          data-disabled={String(!!o.disabled)}
          data-badge={o.badgeText ?? ''}
        >
          <span data-testid="label">{o.label}</span>
          <span data-testid="description">{o.description ?? ''}</span>
        </li>
      ))}
    </ul>
  ),
}));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => null }));

import { ComboTemplatesPicker } from './ComboTemplatesPicker';

const tpl = (id: string, needs: { fixed: number; groups: number[]; upgrades: number }) => ({
  id,
  name: `Template ${id}`,
  family: 'ala_carte',
  published: true,
  print_size: { width_mm: 105, height_mm: 148 },
  needs,
});

const part = (code: string, group: string | null, extra: Record<string, unknown> = {}) => ({
  product_id: `id-${code}`,
  code,
  name: code,
  choice_group: group,
  ...extra,
});

const S1 = [
  ...['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'].map((c) => part(c, 'Kitchen tap')),
  part('SRTKT71SS', null, { is_upgrade: true }),
];
const S2 = [part('SRTWT7449-BL', null)];
const S3 = [part('SRTWT7449-BL', 'Tap colour'), part('SRTWT7449-RG', 'Tap colour')];
const S4 = [part('SRTMCB8083-BL', null), part('SRTWT6203-GM', null)];

type PickerProps = React.ComponentProps<typeof ComboTemplatesPicker> & { parts?: unknown[] };
const Picker = ComboTemplatesPicker as unknown as React.ComponentType<PickerProps>;

function draw(parts?: unknown[]) {
  render(<Picker idPrefix="c" value={[]} onChange={vi.fn()} parts={parts as PickerProps['parts']} />);
}
const row = (id: string) => screen.getByTestId(`opt-${id}`);
const description = (id: string) => within(row(id)).getByTestId('description').textContent;

describe('ComboTemplatesPicker with the combo parts', () => {
  it('S1: shows the needs in the combos own words', () => {
    templates.mockReturnValue([tpl('a', { fixed: 0, groups: [3], upgrades: 1 })]);
    draw(S1);
    expect(description('a')).toBe('105 x 148 mm. Needs 3 from Kitchen tap, upgrade');
    expect(row('a').dataset.disabled).toBe('false');
    // The badge now carries the price type (AC-32); these templates have none set.
    expect(row('a').dataset.badge).toBe('Not set');
  });

  it('S1: a template that needs more than the group has is disabled with the reason', () => {
    templates.mockReturnValue([tpl('a', { fixed: 0, groups: [6], upgrades: 0 })]);
    draw(S1);
    expect(row('a').dataset.disabled).toBe('true');
    expect(row('a').dataset.badge).toBe('Not set / Does not fit');
    expect(description('a')).toBe('Needs 6 from Kitchen tap; this combo has 5');
  });

  it('S2: needs one fixed part', () => {
    templates.mockReturnValue([
      tpl('ok', { fixed: 1, groups: [], upgrades: 0 }),
      tpl('no', { fixed: 2, groups: [], upgrades: 0 }),
    ]);
    draw(S2);
    expect(row('ok').dataset.disabled).toBe('false');
    expect(description('ok')).toMatch(/^105 x 148 mm\. Needs 1 fixed part/);
    expect(row('no').dataset.disabled).toBe('true');
    expect(description('no')).toBe('Needs 2 fixed parts; this combo has 1');
  });

  it('S3: three of two finishes does not fit, two does', () => {
    templates.mockReturnValue([
      tpl('two', { fixed: 0, groups: [2], upgrades: 0 }),
      tpl('three', { fixed: 0, groups: [3], upgrades: 0 }),
    ]);
    draw(S3);
    expect(description('two')).toBe('105 x 148 mm. Needs 2 from Tap colour');
    expect(row('three').dataset.disabled).toBe('true');
    expect(description('three')).toBe('Needs 3 from Tap colour; this combo has 2');
  });

  it('S4: three fixed parts do not fit two', () => {
    templates.mockReturnValue([tpl('a', { fixed: 3, groups: [], upgrades: 0 })]);
    draw(S4);
    expect(row('a').dataset.disabled).toBe('true');
    expect(description('a')).toBe('Needs 3 fixed parts; this combo has 2');
  });

  it('a template that needs nothing says so and fits a combo with no fixed part', () => {
    templates.mockReturnValue([tpl('a', { fixed: 0, groups: [], upgrades: 0 })]);
    draw(S3);
    expect(description('a')).toBe('105 x 148 mm. Needs the main product only');
    expect(row('a').dataset.disabled).toBe('false');
  });

  it('M1: a combo with more fixed parts than the template prints is disabled with the reason', () => {
    templates.mockReturnValue([tpl('a', { fixed: 2, groups: [], upgrades: 0 })]);
    draw([...S4, part('SRTW2600', null), part('SRTWB2380', null)]);
    expect(description('a')).toBe("Prints 2 of this combo's 4 fixed parts");
    expect(row('a').dataset.disabled).toBe('true');
  });

  it('keeps the template name as the label', () => {
    templates.mockReturnValue([tpl('a', { fixed: 9, groups: [], upgrades: 0 })]);
    draw(S4);
    expect(within(row('a')).getByTestId('label').textContent).toBe('Template a');
  });
});

describe('ComboTemplatesPicker without parts (a new combo with no parts yet)', () => {
  it('is today: size only, nothing disabled', () => {
    templates.mockReturnValue([tpl('a', { fixed: 9, groups: [9], upgrades: 9 })]);
    draw(undefined);
    expect(description('a')).toBe('105 x 148 mm');
    expect(row('a').dataset.disabled).toBe('false');
  });
});
