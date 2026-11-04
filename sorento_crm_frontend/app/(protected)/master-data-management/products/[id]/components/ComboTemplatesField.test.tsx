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
const start = vi.fn();
const deferredInputs: Array<Record<string, unknown>> = [];
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: Record<string, unknown>) => {
    deferredInputs.push(input);
    return { start, isPending: false };
  },
}));

vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  comboTagTemplatesKey: (id: string) => ['combo-tag-templates', id],
  useComboTagTemplates: () => linked(),
  useSetComboTagTemplates: () => ({ mutate: save, isPending: false }),
  usePriceTagTemplateOptions: () => ({ data: [], error: null, refetch: vi.fn() }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) => (
    <div>
      <span data-testid="chosen">{value.join(',')}</span>
      <button type="button" onClick={() => onChange([...value, 'c'])}>add c</button>
      <button type="button" onClick={() => onChange(value.filter((v) => v !== 'a'))}>drop a</button>
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
    start.mockReset();
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

  it('an untick parks an unlink with a countdown instead of saving, and keeps the link meanwhile', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b')], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    fireEvent.click(screen.getByText('drop a'));
    expect(save).not.toHaveBeenCalled();
    expect(start).toHaveBeenCalled();
    const last = deferredInputs[deferredInputs.length - 1];
    expect(last.actionKey).toBe('combo.unlink_tag_templates');
    expect(last.entityType).toBe('product_combo');
    expect(last.entityId).toBe('cb1');
    expect(last.payload).toEqual({ template_ids: ['a'] });
    // Nothing is committed until the window lapses: Cancel leaves the links as they were.
    expect(screen.getByTestId('chosen')).toHaveTextContent('a,b');
  });

  it('an add saves at once without a countdown', () => {
    granted.add('dealer_kit.tag_templates.manage');
    linked.mockReturnValue({ data: [row('a'), row('b')], isLoading: false, isError: false });
    render(<ComboTemplatesField comboId="cb1" />);
    fireEvent.click(screen.getByText('add c'));
    expect(save).toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
  });
});
