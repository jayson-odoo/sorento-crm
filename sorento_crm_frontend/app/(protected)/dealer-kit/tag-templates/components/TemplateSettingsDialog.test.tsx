/**
 * PRICETAG-DESIGNER-GAPS item 4: the name, family and print size of an
 * existing template are editable. A size change warns that layers keep their
 * place and may need moving.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// A native select stands in, so the test can read the offered families.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select aria-label="Family" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { TemplateSettingsDialog } from './TemplateSettingsDialog';

const LAYERS = [
  { id: 'a', type: 'shape', x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 20 },
  { id: 'b', type: 'shape', x_mm: 50, y_mm: 10, width_mm: 30, height_mm: 30 },
] as TagLayer[];

function renderDialog(overrides: Partial<React.ComponentProps<typeof TemplateSettingsDialog>> = {}) {
  const onSave = vi.fn(async () => {});
  const onOpenChange = vi.fn();
  render(
    <TemplateSettingsDialog
      open
      onOpenChange={onOpenChange}
      initial={{ name: 'Wash Basin Combo Price Tag', family: 'sink_combo', width_mm: 85, height_mm: 130 }}
      layers={LAYERS}
      onSave={onSave}
      {...overrides}
    />,
  );
  return { onSave, onOpenChange };
}

function family() {
  return screen.getByRole('combobox', { name: 'Family' }) as HTMLSelectElement;
}

describe('TemplateSettingsDialog', () => {
  it('opens filled with the template current settings', () => {
    renderDialog();
    expect(screen.getByLabelText('Name')).toHaveValue('Wash Basin Combo Price Tag');
    expect(family().value).toBe('sink_combo');
    expect(screen.getByLabelText('Width (mm)')).toHaveValue(85);
    expect(screen.getByLabelText('Height (mm)')).toHaveValue(130);
  });

  it('saves a new name and family, trimmed', async () => {
    const { onSave, onOpenChange } = renderDialog();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '  Kitchen Sink with 1 Tap  ' } });
    fireEvent.change(family(), { target: { value: 'ala_carte' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        name: 'Kitchen Sink with 1 Tap',
        family: 'ala_carte',
        width_mm: 85,
        height_mm: 130,
      }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('will not save a blank name', () => {
    const { onSave } = renderDialog();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('shows no size warning while the size is unchanged', () => {
    renderDialog();
    expect(screen.queryByText(/may need moving/i)).toBeNull();
  });

  it('warns that layers may need moving once the size changes, with the count cut off', () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText('Width (mm)'), { target: { value: '70' } });
    expect(screen.getByText(/may need moving/i)).toBeInTheDocument();
    expect(screen.getByText(/1 layer sits outside 70 x 130 mm/i)).toBeInTheDocument();
  });

  it('says the live version keeps its size until the next publish', () => {
    renderDialog({ isLive: true });
    fireEvent.change(screen.getByLabelText('Height (mm)'), { target: { value: '100' } });
    expect(screen.getByText(/live version keeps its size until you publish/i)).toBeInTheDocument();
  });

  it('saves a new size', async () => {
    const { onSave } = renderDialog();
    fireEvent.change(screen.getByLabelText('Width (mm)'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('Height (mm)'), { target: { value: '70' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ width_mm: 100, height_mm: 70 })),
    );
  });

  it('refuses a size under 10 mm', () => {
    const { onSave } = renderDialog();
    fireEvent.change(screen.getByLabelText('Width (mm)'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it('offers only price tag families on a price tag template', () => {
    renderDialog();
    const values = Array.from(family().options).map((o) => o.value);
    expect(values).toContain('ala_carte');
    expect(values).not.toContain('spec_page');
  });

  it('offers only spec sheet families on a spec sheet template', () => {
    renderDialog({ initial: { name: 'Cover', family: 'spec_cover', width_mm: 210, height_mm: 297 } });
    const values = Array.from(family().options).map((o) => o.value);
    expect(values).toEqual(['spec_cover', 'spec_page']);
  });

  it('keeps a family no longer in the list as an option, so it is not blanked', () => {
    renderDialog({ initial: { name: 'Old', family: 'toilet', width_mm: 85, height_mm: 58 } });
    expect(family().value).toBe('toilet');
  });

  it('shows the save error and stays open', async () => {
    const onSave = vi.fn(async () => {
      throw new Error('Name taken');
    });
    const { onOpenChange } = renderDialog({ onSave });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Name taken')).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
