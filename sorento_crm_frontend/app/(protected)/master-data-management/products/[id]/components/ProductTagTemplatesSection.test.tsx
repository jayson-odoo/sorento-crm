/** PRICETAG-TEMPLATE-PER-PRODUCT AC-4: the product page's "Price tag templates" card. */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const linked = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useProductTagTemplates: () => linked(),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
  useSetProductTagTemplates: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ value }: { value: string[] }) => <div data-testid="picker">{value.join(',')}</div>,
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
});
