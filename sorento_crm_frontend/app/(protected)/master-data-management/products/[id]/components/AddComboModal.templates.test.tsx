/**
 * PRICETAG-LPSP S6, AC-24: the combo modal carries the price tag templates field.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The modal asks for a name only.
 *
 * Contract: with `dealer_kit.tag_templates.manage` the modal shows "Price tag templates" (a
 * multi select of the price tag templates) and, once two or more are chosen, a "Default template"
 * select among the chosen ones; Add combo creates the combo, then saves the links through
 * `useSetComboTagTemplates().mutateAsync({ combo_id, template_ids, default_template_id })`. With no
 * templates chosen nothing is saved. Without the permission the field is not drawn.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const createCombo = vi.fn();
vi.mock('../../hooks/useProductCombos', () => ({
  useCreateProductCombo: () => ({ mutateAsync: createCombo, isPending: false }),
}));

const saveLinks = vi.fn();
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  usePriceTagTemplateOptions: () => ({
    data: [
      { id: 't1', name: 'Combo A', family: 'ala_carte', print_size: { width_mm: 80, height_mm: 50 }, published_version_id: 'v1' },
      { id: 't2', name: 'Combo B', family: 'ala_carte', print_size: { width_mm: 80, height_mm: 50 }, published_version_id: 'v2' },
    ],
    error: null,
    refetch: vi.fn(),
  }),
  useSetComboTagTemplates: () => ({ mutateAsync: saveLinks, isPending: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    placeholder?: string;
  }) => (
    <div aria-label={placeholder ?? 'multi'}>
      <button type="button" onClick={() => onChange(['t1'])}>choose one</button>
      <button type="button" onClick={() => onChange(['t1', 't2'])}>choose two</button>
      <span data-testid="chosen">{value.join(',')}</span>
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

import { AddComboModal } from './AddComboModal';

function open(onCreated = vi.fn()) {
  render(<AddComboModal open onOpenChange={vi.fn()} productId="host-1" onCreated={onCreated} />);
  return onCreated;
}

async function addCombo(name = '3 in 1') {
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: name } });
  fireEvent.click(screen.getByRole('button', { name: 'Add combo' }));
  await waitFor(() => expect(createCombo).toHaveBeenCalled());
}

describe('AddComboModal templates (AC-24)', () => {
  beforeEach(() => {
    granted.clear();
    createCombo.mockReset();
    saveLinks.mockReset();
    createCombo.mockResolvedValue({ id: 'new-combo' });
    saveLinks.mockResolvedValue([]);
  });

  it('shows the templates field to a template manager', () => {
    granted.add('dealer_kit.tag_templates.manage');
    open();
    expect(screen.getByText('Price tag templates')).toBeInTheDocument();
  });

  it('does not draw the field without the manage permission', () => {
    granted.add('dealer_kit.tag_templates.view');
    open();
    expect(screen.queryByText('Price tag templates')).toBeNull();
  });

  it('offers a default only once two templates are chosen', () => {
    granted.add('dealer_kit.tag_templates.manage');
    open();
    expect(screen.queryByLabelText('Default template')).toBeNull();
    fireEvent.click(screen.getByText('choose one'));
    expect(screen.queryByLabelText('Default template')).toBeNull();
    fireEvent.click(screen.getByText('choose two'));
    expect(screen.getByLabelText('Default template')).toBeInTheDocument();
  });

  it('creates the combo, then links the chosen templates with the default', async () => {
    granted.add('dealer_kit.tag_templates.manage');
    const onCreated = open();
    fireEvent.click(screen.getByText('choose two'));
    fireEvent.change(screen.getByLabelText('Default template'), { target: { value: 't2' } });
    await addCombo();

    await waitFor(() => expect(saveLinks).toHaveBeenCalledTimes(1));
    expect(createCombo).toHaveBeenCalledWith({ name: '3 in 1' });
    expect(saveLinks).toHaveBeenCalledWith({
      combo_id: 'new-combo',
      template_ids: ['t1', 't2'],
      default_template_id: 't2',
    });
    expect(onCreated).toHaveBeenCalledWith('new-combo');
  });

  it('a single chosen template needs no default of its own', async () => {
    granted.add('dealer_kit.tag_templates.manage');
    open();
    fireEvent.click(screen.getByText('choose one'));
    await addCombo();
    await waitFor(() => expect(saveLinks).toHaveBeenCalledTimes(1));
    const sent = saveLinks.mock.calls[0][0];
    expect(sent.combo_id).toBe('new-combo');
    expect(sent.template_ids).toEqual(['t1']);
    expect(sent.default_template_id == null || sent.default_template_id === 't1').toBe(true);
  });

  it('saves no links when no template was chosen', async () => {
    granted.add('dealer_kit.tag_templates.manage');
    open();
    await addCombo();
    expect(saveLinks).not.toHaveBeenCalled();
  });

  it('without the permission the combo is created as before and nothing is linked', async () => {
    open();
    await addCombo();
    expect(createCombo).toHaveBeenCalledWith({ name: '3 in 1' });
    expect(saveLinks).not.toHaveBeenCalled();
  });
});
