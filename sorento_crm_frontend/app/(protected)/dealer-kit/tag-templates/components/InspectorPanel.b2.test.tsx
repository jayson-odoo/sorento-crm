/**
 * PRICETAG-DESIGNER-FEEDBACK B2: the inspector wiring.
 *
 * AC-1.6 the Content box editor gets the inspector's font list (`fontOptions`, uploaded fonts
 * included), so its toolbar shows the "Font" picker and the "Font size" field.
 * AC-5.1 the Accessories box shows "Columns" and "Rows" selects (Auto, 1-4); "One column or row" is gone.
 * AC-7.6 the Spec icons box shows the same Columns / Rows selects.
 * AC-8.2 the Spec icons box lists the icons this tag's product would show, one checkbox each
 * (ticked = shown); unticking writes `hiddenIconIds`.
 *
 * Invented for AC-8.2 (the coder must match): prop `featureIconChoices?: { id: string; name: string;
 * url?: string | null }[]` = the icons the previewed product would show BEFORE `hiddenIconIds` is
 * applied; one checkbox per icon, accessible name = the icon name.
 *
 * Written test-FIRST through props and rendered output only.
 */
import '@/test-utils/prosemirrorGeometry';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const selects = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
    placeholder?: unknown;
  }) => {
    selects.props.push(props as Record<string, unknown>);
    return (
      <select aria-label={props['aria-label']} value={props.value ?? ''} onChange={(e) => props.onChange?.(e.target.value)}>
        <option value="" />
        {(props.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

beforeEach(() => {
  selects.props.length = 0;
});

const optionLabels = (label: string) =>
  Array.from(screen.getByLabelText(label).querySelectorAll('option'))
    .map((o) => o.textContent ?? '')
    .filter(Boolean);

function textLayer(): TagLayer {
  return {
    id: 't1', type: 'text', x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 12, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: {
      kind: 'text', text: 'Hello', fontFamily: 'DM Sans', fontSize: 12, fontWeight: 400, color: '#000000',
      align: 'left', lineHeight: 1.2, letterSpacing: 0,
    },
  } as TagLayer;
}

const CARD = {
  width_mm: 30,
  height_mm: 20,
  elements: [{ id: 'name', kind: 'text', field: 'name', x_mm: 1, y_mm: 1, width_mm: 20, height_mm: 5 }],
};

function accessoriesBox(over: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'acc1', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 80, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), card: CARD, ...over },
  } as TagLayer;
}

function iconsLayer(props: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'fi1', type: 'feature_icons', x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 10, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1.5, align: 'left', ...props },
  } as unknown as TagLayer;
}

function mount(layer: TagLayer, extra: Record<string, unknown> = {}) {
  const onUpdateProps = vi.fn();
  render(
    <InspectorPanel
      layer={layer}
      onUpdate={vi.fn()}
      onUpdateProps={onUpdateProps}
      resolvedText={null}
      onInsertField={vi.fn()}
      {...(extra as Record<string, never>)}
    />,
  );
  return onUpdateProps;
}

describe('AC-1.6: the Content box editor gets the font list', () => {
  it('shows the Font picker with the inspector fonts, uploaded ones included, and the Font size field', async () => {
    mount(textLayer(), {
      fontOptions: [
        { value: 'DM Sans', label: 'DM Sans' },
        { value: 'ZZT Brand Upload', label: 'ZZT Brand Upload' },
      ],
    });
    await waitFor(() => expect(screen.getByLabelText('Font')).toBeInTheDocument());
    expect(optionLabels('Font')).toEqual(expect.arrayContaining(['DM Sans', 'ZZT Brand Upload']));
    expect(screen.getByLabelText('Font size')).toBeInTheDocument();
  });
});

describe('AC-5.1: Accessories box Columns and Rows', () => {
  it('shows Columns and Rows, each Auto, 1, 2, 3, 4', () => {
    mount(accessoriesBox());
    expect(optionLabels('Columns')).toEqual(['Auto', '1', '2', '3', '4']);
    expect(optionLabels('Rows')).toEqual(['Auto', '1', '2', '3', '4']);
  });

  it('choosing Rows 2 writes rows: 2 (a number), Auto writes rows: auto', () => {
    const onUpdateProps = mount(accessoriesBox());
    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: '2' } });
    expect(onUpdateProps).toHaveBeenLastCalledWith('acc1', expect.objectContaining({ rows: 2 }));
    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: 'auto' } });
    expect(onUpdateProps).toHaveBeenLastCalledWith('acc1', expect.objectContaining({ rows: 'auto' }));
  });

  it('shows the current Rows choice', () => {
    mount(accessoriesBox({ rows: 3 }));
    expect((screen.getByLabelText('Rows') as HTMLSelectElement).value).toBe('3');
  });

  it('the old "One column or row" label is gone', () => {
    mount(accessoriesBox());
    expect(screen.getByLabelText('Rows')).toBeInTheDocument();
    expect(selects.props.some((p) => p.placeholder === 'One column or row')).toBe(false);
    expect(screen.queryByText('One column or row')).toBeNull();
  });
});

describe('AC-7.6: Spec icons box Columns and Rows', () => {
  it('shows Columns and Rows, each Auto, 1, 2, 3, 4', () => {
    mount(iconsLayer());
    expect(optionLabels('Columns')).toEqual(['Auto', '1', '2', '3', '4']);
    expect(optionLabels('Rows')).toEqual(['Auto', '1', '2', '3', '4']);
  });

  it('writes columns and rows on the icons layer', () => {
    const onUpdateProps = mount(iconsLayer());
    fireEvent.change(screen.getByLabelText('Columns'), { target: { value: '2' } });
    expect(onUpdateProps).toHaveBeenLastCalledWith('fi1', expect.objectContaining({ columns: 2, iconSize_mm: 8 }));
    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: 'auto' } });
    expect(onUpdateProps).toHaveBeenLastCalledWith('fi1', expect.objectContaining({ rows: 'auto' }));
  });
});

describe('AC-8.2: Spec icons choice per product on this tag', () => {
  const CHOICES = [
    { id: 'cold', name: 'Cold', url: 'https://cdn.test/cold.png' },
    { id: 'hot', name: 'Hot', url: 'https://cdn.test/hot.png' },
  ];

  it('one checkbox per icon the product would show, ticked = shown', () => {
    mount(iconsLayer({ hiddenIconIds: ['cold'] }), { featureIconChoices: CHOICES });
    expect(screen.getByRole('checkbox', { name: 'Cold' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Hot' })).toBeChecked();
  });

  it('unticking hides that icon, ticking shows it again', () => {
    const onUpdateProps = mount(iconsLayer({ hiddenIconIds: ['cold'] }), { featureIconChoices: CHOICES });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Hot' }));
    const hidden = onUpdateProps.mock.calls.at(-1)?.[1]?.hiddenIconIds as string[] | undefined;
    expect(onUpdateProps.mock.calls.at(-1)?.[0]).toBe('fi1');
    expect([...(hidden ?? [])].sort()).toEqual(['cold', 'hot']);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Cold' }));
    expect(onUpdateProps).toHaveBeenLastCalledWith('fi1', expect.objectContaining({ hiddenIconIds: [] }));
  });

  it('with nothing hidden every icon is ticked', () => {
    mount(iconsLayer(), { featureIconChoices: CHOICES });
    expect(screen.getByRole('checkbox', { name: 'Cold' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Hot' })).toBeChecked();
  });
});
