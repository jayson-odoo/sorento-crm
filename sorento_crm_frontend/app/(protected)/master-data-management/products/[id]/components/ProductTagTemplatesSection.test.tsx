/** PRICETAG-TEMPLATE-PER-PRODUCT AC-4: the product page's "Price tag templates" card. */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const linked = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useProductTagTemplates: () => linked(),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
  productTagTemplatesKey: (id: string) => ['product-tag-templates', id],
  useSetProductTagTemplates: () => ({ mutate: save, isPending: false }),
}));

const save = vi.fn();
const start = vi.fn();
const deferredInputs: Array<Record<string, unknown>> = [];
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: Record<string, unknown>) => {
    deferredInputs.push(input);
    return { start, isPending: false };
  },
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) => (
    <div>
      <div data-testid="picker">{value.join(',')}</div>
      <button type="button" onClick={() => onChange([...value, 'c'])}>add c</button>
      <button type="button" onClick={() => onChange(value.filter((v) => v !== 'a'))}>drop a</button>
    </div>
  ),
}));

import ProductTagTemplatesSection from './ProductTagTemplatesSection';

const row = (id: string, published = true) => ({
  id,
  name: `Template ${id}`,
  family: 'ala_carte',
  published,
  width_mm: 80,
  height_mm: 50,
});

describe('ProductTagTemplatesSection', () => {
  beforeEach(() => {
    granted.clear();
    linked.mockReset();
    save.mockReset();
    start.mockReset();
    deferredInputs.length = 0;
  });

  it('is not drawn without the view permission', () => {
    linked.mockReturnValue({ data: [], isLoading: false, isError: false });
    const { container } = render(<ProductTagTemplatesSection productId="p1" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the linked templates read-only to a viewer, drafts marked', () => {
    granted.add('dealer_kit.tag_templates.view');
    linked.mockReturnValue({ data: [row('a'), row('b', false)], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.getByText('Template a')).toBeInTheDocument();
    expect(screen.getByText('(Draft)')).toBeInTheDocument();
    expect(screen.queryByTestId('picker')).toBeNull();
  });

  it('gives a manager the picker holding the current links', () => {
    granted.add('dealer_kit.tag_templates.view');
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a')], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.getByTestId('picker')).toHaveTextContent('a');
  });

  it('has an explicit empty state with no button', () => {
    granted.add('dealer_kit.tag_templates.view');
    linked.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    expect(screen.getByText('No price tag templates')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('an add saves at once, keeping every current link', () => {
    granted.add('dealer_kit.tag_templates.view');
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b')], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalledWith(['a', 'b', 'c']);
    expect(start).not.toHaveBeenCalled();
  });

  it('an untick parks an unlink with a countdown instead of saving', () => {
    granted.add('dealer_kit.tag_templates.view');
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b')], isLoading: false, isError: false });
    render(<ProductTagTemplatesSection productId="p1" />);
    fireEvent.click(screen.getByText('drop a'));
    expect(save).not.toHaveBeenCalled();
    expect(start).toHaveBeenCalled();
    const last = deferredInputs[deferredInputs.length - 1];
    expect(last.actionKey).toBe('product_tag_template.unlink');
    expect(last.payload).toEqual({ template_ids: ['a'] });
  });
});
