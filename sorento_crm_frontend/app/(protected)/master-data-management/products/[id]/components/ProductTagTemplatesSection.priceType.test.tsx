/**
 * PRICETAG-COMBO-FORMAT AC-32 (product card): the product's "Price tag templates" card shows each
 * template's price type and sets one default LP and one default SP, independently, through
 * `default_list_template_id` / `default_selling_template_id` (the wire names in the contract).
 * The SP default control does not offer an LP-only template.
 *
 * Written test-FIRST. The card has one "Default template" select (`default_template_id`) today.
 * The two controls are found by an accessible name matching /default LP/i and /default SP/i.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: (slug: string) => granted.has(slug) }));

const linked = vi.fn();
const save = vi.fn();
const options = vi.hoisted(() => ({ rows: [] as unknown[] }));
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useProductTagTemplates: () => linked(),
  usePriceTagTemplateOptions: () => ({ data: options.rows, error: null, refetch: vi.fn() }),
  productTagTemplatesKey: (id: string) => ['product-tag-templates', id],
  useSetProductTagTemplates: () => ({ mutate: save, isPending: false }),
}));
vi.mock('@/hooks/useDeferredAction', () => ({ useDeferredAction: () => ({ start: vi.fn(), isPending: false }) }));

type Opt = { value: string; label: string; description?: string; badgeText?: string };
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ options = [], selectedOptions = [] }: { options?: Opt[]; selectedOptions?: Opt[] }) => (
    <ul>
      {[...options, ...selectedOptions].map((o, i) => (
        <li key={`${o.value}-${i}`} data-testid={`opt-${o.value}`} data-description={o.description ?? ''}>
          {[o.label, o.description, o.badgeText].filter(Boolean).join(' | ')}
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

import ProductTagTemplatesSection from './ProductTagTemplatesSection';

const link = (id: string, name: string, price_type: string | null, flags: { l?: boolean; s?: boolean } = {}) => ({
  id,
  name,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type,
  default_list: !!flags.l,
  default_selling: !!flags.s,
  is_default: !!(flags.l || flags.s),
});

const LP = link('lp', 'Alpha', 'list', { l: true });
const SP = link('sp', 'Beta', 'selling', { s: true });
const BOTH = link('both', 'Gamma', 'both');
const NONE = link('none', 'Delta', null);

const manager = () => {
  granted.add('dealer_kit.tag_templates.view');
  granted.add('dealer_kit.tag_templates.manage');
};
const defaultSelect = (type: 'LP' | 'SP') => screen.getByLabelText(new RegExp(`default ${type}`, 'i'));
const optionIds = (select: HTMLElement) =>
  Array.from(select.querySelectorAll('option')).map((o) => o.getAttribute('value')).filter(Boolean);

beforeEach(() => {
  granted.clear();
  linked.mockReset();
  save.mockReset();
  options.rows = [LP, SP, BOTH, NONE].map((r) => ({
    id: r.id,
    name: r.name,
    family: 'ala_carte',
    published_version_id: 'v1',
    print_size: { width_mm: 80, height_mm: 50 },
    price_type: r.price_type,
  }));
});

describe('ProductTagTemplatesSection price types (AC-32)', () => {
  it('AC-32: a manager sees each linked template with its price type', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH, NONE], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    const read = (id: string) => screen.getAllByTestId(`opt-${id}`).map((n) => n.textContent).join(' ');
    expect(read('lp')).toMatch(/\bLP\b/);
    expect(read('sp')).toMatch(/\bSP\b/);
    expect(read('both')).toContain('LP & SP');
    expect(read('none')).toContain('Not set');
  });

  it('AC-32: a viewer reads the price type on each template badge', () => {
    granted.add('dealer_kit.tag_templates.view');
    linked.mockReturnValue({ data: [LP, BOTH, NONE], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    expect(screen.getByText(/Alpha/).parentElement?.textContent).toMatch(/\bLP\b/);
    expect(screen.getByText(/Gamma/).parentElement?.textContent).toContain('LP & SP');
    expect(screen.getByText(/Delta/).parentElement?.textContent).toContain('Not set');
  });

  it('AC-32: the SP default control offers no LP-only template, the LP one no SP-only template', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH, NONE], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    expect(optionIds(defaultSelect('SP'))).toEqual(expect.arrayContaining(['sp', 'both', 'none']));
    expect(optionIds(defaultSelect('SP'))).not.toContain('lp');
    expect(optionIds(defaultSelect('LP'))).toEqual(expect.arrayContaining(['lp', 'both', 'none']));
    expect(optionIds(defaultSelect('LP'))).not.toContain('sp');
  });

  it('AC-32: choosing the default LP saves default_list_template_id and keeps the SP default', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    fireEvent.change(defaultSelect('LP'), { target: { value: 'both' } });

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        template_ids: ['lp', 'sp', 'both'],
        default_list_template_id: 'both',
        default_selling_template_id: 'sp',
      }),
    );
  });

  it('AC-32: choosing the default SP saves default_selling_template_id and keeps the LP default', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    fireEvent.change(defaultSelect('SP'), { target: { value: 'both' } });

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        default_selling_template_id: 'both',
        default_list_template_id: 'lp',
      }),
    );
  });

  it('AC-32: clearing the default SP saves null for it only', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);

    fireEvent.change(defaultSelect('SP'), { target: { value: '' } });

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ default_selling_template_id: null, default_list_template_id: 'lp' }),
    );
  });
});

const LABEL: Record<string, string> = { lp: 'LP', sp: 'SP', both: 'LP & SP', none: 'Not set' };

describe('price type as the option description (R20)', () => {
  it('R20: every option of the link multi-select has its price type as its description', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH, NONE], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    for (const id of Object.keys(LABEL)) {
      const options = screen.getAllByTestId(`opt-${id}`);
      // The type leads the description; a size may follow after ' / '.
      expect(options.some((o) => (o.dataset.description ?? '').split(' / ')[0] === LABEL[id]), id).toBe(true);
    }
  });

  it('R20: the Default LP and Default SP options carry it too', () => {
    manager();
    linked.mockReturnValue({ data: [LP, SP, BOTH, NONE], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    for (const type of ['LP', 'SP'] as const) {
      const options = Array.from(defaultSelect(type).querySelectorAll('option')).filter((o) => o.getAttribute('value'));
      expect(options.length).toBeGreaterThan(0);
      for (const o of options) {
        expect((o as HTMLElement).dataset.description, `${type} ${o.getAttribute('value')}`).toBe(LABEL[o.getAttribute('value') as string]);
      }
    }
  });
});
