/**
 * PRICETAG-LPSP fix round S3: an EXISTING combo gets its price tag templates (and default) on the
 * product page, for `dealer_kit.tag_templates.manage` only, saved through the combo PUT.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const linked = vi.fn();
const save = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useComboTagTemplates: () => linked(),
  useSetComboTagTemplates: () => ({ mutate: save, isPending: false }),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) => (
    <div>
      <span data-testid="chosen">{value.join(',')}</span>
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
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}));

import { ComboTemplatesField } from './ComboTemplatesField';

const row = (id: string, isDefault = false) => ({
  id,
  name: `Template ${id}`,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  is_default: isDefault,
});

describe('ComboTemplatesField (existing combo)', () => {
  beforeEach(() => {
    granted.clear();
    linked.mockReset();
    save.mockReset();
  });

  it('is not drawn without the manage permission', () => {
    granted.add('dealer_kit.tag_templates.view');
    linked.mockReturnValue({ data: [row('a')], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    expect(screen.queryByText('Price tag templates')).toBeNull();
  });

  it('shows the current links and the default of the combo', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    expect(screen.getByText('Price tag templates')).toBeInTheDocument();
    expect(screen.getByTestId('chosen')).toHaveTextContent('a,b');
    expect((screen.getByLabelText('Default template') as HTMLSelectElement).value).toBe('b');
  });

  it('adding a template saves through the combo PUT and keeps the chosen default', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalledWith({
      combo_id: 'cb1',
      template_ids: ['a', 'b', 'c'],
      default_template_id: 'b',
    });
  });

  it('changing the default saves it', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b', true)], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    fireEvent.change(screen.getByLabelText('Default template'), { target: { value: 'a' } });
    expect(save).toHaveBeenCalledWith({
      combo_id: 'cb1',
      template_ids: ['a', 'b'],
      default_template_id: 'a',
    });
  });

  it('adding a 2nd template to a lone link stores no default of its own', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a', true)], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalledWith({
      combo_id: 'cb1',
      template_ids: ['a', 'c'],
      default_template_id: null,
    });
  });
});
