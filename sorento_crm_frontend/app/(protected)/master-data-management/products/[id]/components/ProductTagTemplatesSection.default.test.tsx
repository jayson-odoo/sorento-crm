/**
 * PRICETAG-LPSP S6, AC-24: the product page chooses the DEFAULT among its linked templates.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The card has no default choice yet.
 *
 * Contract: a manager with two or more links sees a select named "Default template" listing
 * only the linked templates and showing the row with `is_default`; picking one saves
 * `{ template_ids, default_template_id }` through `useSetProductTagTemplates().mutate` (the wire
 * body); an add keeps the current default; one link needs no choice (it is implicitly the
 * default); a viewer reads the default as a "Default" mark on its row.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const linked = vi.fn();
const save = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useProductTagTemplates: () => linked(),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
  productTagTemplatesKey: (id: string) => ['product-tag-templates', id],
  useSetProductTagTemplates: () => ({ mutate: save, isPending: false }),
}));

vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ start: vi.fn(), isPending: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) => (
    <div>
      <div data-testid="picker">{value.join(',')}</div>
      <button type="button" onClick={() => onChange([...value, 'c'])}>add c</button>
    </div>
  ),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value ?? ''}
      onChange={(event) => props.onChange?.(event.target.value)}
    >
      <option value="">-</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import ProductTagTemplatesSection from './ProductTagTemplatesSection';

const row = (id: string, isDefault = false) => ({
  id,
  name: `Template ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type: null,
  is_default: isDefault,
  // The release backfill: an old default is the default for both types.
  default_list: isDefault,
  default_selling: isDefault,
});

const manager = () => {
  granted.add('dealer_kit.tag_templates.view');
  granted.add('dealer_kit.tag_templates.manage');
};

describe('ProductTagTemplatesSection default (AC-24)', () => {
  beforeEach(() => {
    granted.clear();
    linked.mockReset();
    save.mockReset();
  });

  it('shows a manager the default among the linked templates', () => {
    manager();
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    for (const name of ['Default LP template', 'Default SP template']) {
      const select = screen.getByLabelText(name) as HTMLSelectElement;
      expect(select.value, name).toBe('b');
      const offered = within(select).getAllByRole('option').map((o) => o.textContent);
      expect(offered).toContain('Template a');
      expect(offered).toContain('Template b');
      expect(offered).not.toContain('Template c');
    }
  });

  it('choosing another default saves it with every current link', () => {
    manager();
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    fireEvent.change(screen.getByLabelText('Default LP template'), { target: { value: 'a' } });
    expect(save).toHaveBeenCalledTimes(1);
    // The SP default is untouched (AC-32: set per type).
    expect(save).toHaveBeenCalledWith({
      template_ids: ['a', 'b'],
      default_list_template_id: 'a',
      default_selling_template_id: 'b',
    });
  });

  it('adding a template keeps the current default', () => {
    manager();
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalledWith({
      template_ids: ['a', 'b', 'c'],
      default_list_template_id: 'b',
      default_selling_template_id: 'b',
    });
  });

  it('adding a 2nd template to a lone link does not store the lone link as the default', () => {
    manager();
    linked.mockReturnValue({ data: [row('a', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalledWith({
      template_ids: ['a', 'c'],
      default_list_template_id: null,
      default_selling_template_id: null,
    });
  });

  it('offers no default choice for a single link, which is its own default', () => {
    manager();
    linked.mockReturnValue({ data: [row('a', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.queryByLabelText(/^Default (LP |SP )?template$/)).toBeNull();
  });

  it('offers no default choice with no links', () => {
    manager();
    linked.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.queryByLabelText(/^Default (LP |SP )?template$/)).toBeNull();
  });

  it('a viewer reads the default as a mark on its row and cannot change it', () => {
    granted.add('dealer_kit.tag_templates.view');
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.queryByLabelText(/^Default (LP |SP )?template$/)).toBeNull();
    for (const mark of ['Default LP', 'Default SP']) {
      const marks = screen.getAllByText(mark);
      expect(marks, mark).toHaveLength(1);
      expect(marks[0].closest('[title]')?.getAttribute('title')).toBe('Template b');
    }
  });
});
