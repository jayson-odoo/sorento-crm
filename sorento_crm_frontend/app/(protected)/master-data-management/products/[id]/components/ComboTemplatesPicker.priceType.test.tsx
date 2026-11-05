/**
 * PRICETAG-COMBO-FORMAT AC-32 (combo picker): each template shows its price type (LP / SP /
 * LP & SP / Not set); the default is set per type ("default LP" and "default SP"), and the SP
 * default control does not offer an LP-only template.
 *
 * Written test-FIRST. The picker has one "Default template" select today.
 *
 * Contract read literally (the contract names no prop or label for the two defaults): the two
 * controls are found by an accessible name matching /default LP/i and /default SP/i, and a pick is
 * observed as the picked template id appearing in the arguments of `onChange`. Option text is read
 * from the option's label, description and badge together.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const templates = vi.hoisted(() => ({ rows: [] as unknown[] }));
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  usePriceTagTemplateOptions: () => ({ data: templates.rows, error: null, refetch: vi.fn() }),
}));

type Opt = { value: string; label: string; description?: string; badgeText?: string };
const text = (o: Opt) => [o.label, o.description, o.badgeText].filter(Boolean).join(' | ');

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ options = [], selectedOptions = [] }: { options?: Opt[]; selectedOptions?: Opt[] }) => (
    <ul>
      {[...options, ...selectedOptions].map((o, i) => (
        <li key={`${o.value}-${i}`} data-testid={`opt-${o.value}`} data-description={o.description ?? ''}>
          {text(o)}
        </li>
      ))}
    </ul>
  ),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    'aria-label'?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string; description?: string }[];
  }) => (
    <select
      aria-label={props['aria-label'] ?? props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value} data-description={o.description ?? ''}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { ComboTemplatesPicker } from './ComboTemplatesPicker';

const tpl = (id: string, name: string, price_type: string | null) => ({
  id,
  name,
  family: 'ala_carte',
  published: true,
  print_size: { width_mm: 85, height_mm: 58 },
  price_type,
});

const ALL = [
  tpl('lp', 'Alpha', 'list'),
  tpl('sp', 'Beta', 'selling'),
  tpl('both', 'Gamma', 'both'),
  tpl('none', 'Delta', null),
];

type Props = React.ComponentProps<typeof ComboTemplatesPicker>;
function draw(value: string[], onChange = vi.fn()) {
  render(
    <ComboTemplatesPicker
      {...({ idPrefix: 'c', value, defaultId: '', onChange } as Props)}
      selectedOptions={value.map((id) => ({ value: id, label: ALL.find((t) => t.id === id)!.name }))}
    />,
  );
  return onChange;
}

const defaultSelect = (type: 'LP' | 'SP') => screen.getByLabelText(new RegExp(`default ${type}`, 'i'));
const optionIds = (select: HTMLElement) =>
  Array.from(select.querySelectorAll('option'))
    .map((o) => o.getAttribute('value'))
    .filter(Boolean);

beforeEach(() => {
  templates.rows = ALL;
});

describe('ComboTemplatesPicker price types (AC-32)', () => {
  it('AC-32: each template shows LP, SP, LP & SP or Not set', () => {
    draw(['lp']);
    const read = (id: string) => screen.getAllByTestId(`opt-${id}`)[0].textContent!;
    expect(read('lp')).toMatch(/\bLP\b/);
    expect(read('lp')).not.toMatch(/\bSP\b/);
    expect(read('sp')).toMatch(/\bSP\b/);
    expect(read('sp')).not.toMatch(/\bLP\b/);
    expect(read('both')).toContain('LP & SP');
    expect(read('none')).toContain('Not set');
  });

  it('AC-32: two links give a default LP and a default SP control', () => {
    draw(['lp', 'sp']);
    expect(defaultSelect('LP')).toBeInTheDocument();
    expect(defaultSelect('SP')).toBeInTheDocument();
  });

  it('AC-32: the SP default control does not offer an LP-only template; the LP one does not offer an SP-only one', () => {
    draw(['lp', 'sp', 'both', 'none']);
    expect(optionIds(defaultSelect('SP'))).toEqual(expect.arrayContaining(['sp', 'both', 'none']));
    expect(optionIds(defaultSelect('SP'))).not.toContain('lp');
    expect(optionIds(defaultSelect('LP'))).toEqual(expect.arrayContaining(['lp', 'both', 'none']));
    expect(optionIds(defaultSelect('LP'))).not.toContain('sp');
  });

  it('AC-32: setting the default LP reports that template and leaves the SP default untouched', () => {
    const onChange = draw(['lp', 'sp']);
    fireEvent.change(defaultSelect('LP'), { target: { value: 'lp' } });

    const reported = JSON.stringify(onChange.mock.calls.at(-1));
    expect(reported).toContain('lp');
    // The SP default was never chosen, so nothing in the report names the SP-only template as a default.
    expect(onChange.mock.calls.at(-1)?.[1]).not.toBe('sp');
  });

  it('AC-32: setting the default SP is its own change', () => {
    const onChange = draw(['lp', 'sp']);
    fireEvent.change(defaultSelect('SP'), { target: { value: 'sp' } });
    expect(JSON.stringify(onChange.mock.calls.at(-1))).toContain('sp');
  });
});

const LABEL: Record<string, string> = { lp: 'LP', sp: 'SP', both: 'LP & SP', none: 'Not set' };

describe('price type as the option description (R20)', () => {
  it('R20: every option of the link multi-select carries its price type as its description', () => {
    draw(['lp']);
    for (const id of Object.keys(LABEL)) {
      const options = screen.getAllByTestId(`opt-${id}`);
      // The type leads the description; a size may follow after ' / '.
      expect(options.some((o) => (o.dataset.description ?? '').split(' / ')[0] === LABEL[id]), id).toBe(true);
    }
  });

  it('R20: the Default LP and Default SP options carry it too', () => {
    draw(['lp', 'sp', 'both', 'none']);
    for (const type of ['LP', 'SP'] as const) {
      const options = Array.from(defaultSelect(type).querySelectorAll('option')).filter((o) => o.getAttribute('value'));
      expect(options.length).toBeGreaterThan(0);
      for (const o of options) {
        expect((o as HTMLElement).dataset.description, `${type} ${o.getAttribute('value')}`).toBe(LABEL[o.getAttribute('value') as string]);
      }
    }
  });
});
