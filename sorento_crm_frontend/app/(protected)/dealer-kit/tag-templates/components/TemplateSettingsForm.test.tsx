/**
 * TAG-TEMPLATE-DUPLICATE item 7 (owner 6 Nov, "please unify these"; owner rule 28 Oct: create
 * and edit forms are identical and use the SAME component). New tag template and the editor's
 * Template settings both render `TemplateSettingsForm`: the same fields in the same order with
 * the same labels and validation, Price type included.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
const createTemplate = vi.hoisted(() => vi.fn());
vi.mock('../../services/tagTemplateService', () => ({ createTemplate }));

import { TagTemplateDialog } from './TagTemplateDialog';
import { TemplateSettingsDialog } from './TemplateSettingsDialog';

/** The form's field labels, top to bottom. */
function fieldLabels(): string[] {
  const form = screen.getByTestId('template-settings-form');
  return Array.from(form.querySelectorAll('[data-field-label]')).map((el) => el.textContent ?? '');
}

const FIELDS = ['Name', 'Family', 'Price type', 'Width (mm)', 'Height (mm)'];

describe('one TemplateSettingsForm for New and Settings', () => {
  it('New shows the shared form: Name, Family, Price type, Width, Height', () => {
    render(<TagTemplateDialog open onOpenChange={vi.fn()} />);
    expect(fieldLabels()).toEqual(FIELDS);
  });

  it('Settings shows the SAME form, Price type included', () => {
    render(
      <TemplateSettingsDialog
        open
        onOpenChange={vi.fn()}
        initial={{ name: 'BF_LP', family: 'ala_carte', price_type: 'list', width_mm: 85, height_mm: 58 }}
        layers={[]}
        onSave={vi.fn(async () => {})}
      />,
    );
    expect(fieldLabels()).toEqual(FIELDS);
    const priceType = screen.getByRole('group', { name: 'Price type' });
    expect(within(priceType).getByRole('radio', { name: 'LP' })).toHaveAttribute('aria-checked', 'true');
  });

  it('Settings saves a changed price type with the other settings', async () => {
    const onSave = vi.fn(async () => {});
    render(
      <TemplateSettingsDialog
        open
        onOpenChange={vi.fn()}
        initial={{ name: 'BF_LP', family: 'ala_carte', price_type: 'list', width_mm: 85, height_mm: 58 }}
        layers={[]}
        onSave={onSave}
      />,
    );
    fireEvent.click(within(screen.getByRole('group', { name: 'Price type' })).getByRole('radio', { name: 'SP' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await vi.waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave).toHaveBeenCalledWith({
      name: 'BF_LP',
      family: 'ala_carte',
      price_type: 'selling',
      width_mm: 85,
      height_mm: 58,
    });
  });

  it('both validate the same way: a blank name disables submit, a size under 10 mm errors', () => {
    const { unmount } = render(<TagTemplateDialog open onOpenChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /create template/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText('Width (mm)'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /create template/i }));
    const newError = screen.getByLabelText('Width (mm)').getAttribute('aria-invalid');
    unmount();

    render(
      <TemplateSettingsDialog
        open
        onOpenChange={vi.fn()}
        initial={{ name: 'BF_LP', family: 'ala_carte', price_type: null, width_mm: 85, height_mm: 58 }}
        layers={[]}
        onSave={vi.fn(async () => {})}
      />,
    );
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '  ' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText('Width (mm)'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByLabelText('Width (mm)').getAttribute('aria-invalid')).toBe(newError);
    expect(newError).toBe('true');
  });
});
