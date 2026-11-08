/**
 * PRICETAG-ACCESSORY-DESIGNER S3: the accessories box inspector (box level) and the element
 * inspector (a card or footer element selected while editing the card).
 *
 * Plan: documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md "S3 Designer";
 * labels from mock v2. Written test-FIRST.
 *
 * Props invented here (the coder must match them), all optional on InspectorPanel:
 *   onEditAccessoryCard(layerId)          "Edit card" button
 *   onEditAccessoryFooter(layerId)        "Edit footer" button
 *   onSaveAccessoryTemplate(layerId)      "Save as accessories template" button
 *   accessoryTemplate: { name, usedIn }   the linked template's facts, shown when props.presetId is set
 *   accessoryEdit: { layerId, target: 'card' | 'footer', elementId: string | null } | null
 *   onUpdateAccessoryElement(elementId, patch)   patch of CardElement fields
 * Detach and "Footer note" go through the existing onUpdateProps(layerId, patch).
 * The element "Shows" control is a select labelled exactly "Shows" (a SearchableSelect with options
 * {value,label}); the dot controls are labelled "Dot size (mm)", "Gap (mm)" and radios "Row" / "Column".
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
// A native select stands in for the Radix picker so the offered options can be read.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value?: string | null;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
    id?: string;
  }) => (
    <select
      aria-label={props['aria-label']}
      id={props.id}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" />
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { defaultAccessoriesProps, type TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const CARD = {
  width_mm: 40,
  height_mm: 30,
  elements: [
    { id: 'pic', kind: 'picture', field: 'picture', x_mm: 0, y_mm: 0, width_mm: 15, height_mm: 15 },
    { id: 'txt', kind: 'text', field: 'name', x_mm: 16, y_mm: 0, width_mm: 24, height_mm: 5 },
    { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 16, y_mm: 15, width_mm: 24, height_mm: 4 },
  ],
};

function box(over: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'acc1',
    type: 'accessories',
    x_mm: 0,
    y_mm: 0,
    width_mm: 60,
    height_mm: 80,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultAccessoriesProps(), ...over },
  } as TagLayer;
}

function mount(layer: TagLayer, extra: Record<string, unknown> = {}) {
  const spies = {
    onUpdate: vi.fn(),
    onUpdateProps: vi.fn(),
    onEditAccessoryCard: vi.fn(),
    onEditAccessoryFooter: vi.fn(),
    onSaveAccessoryTemplate: vi.fn(),
    onUpdateAccessoryElement: vi.fn(),
  };
  render(<InspectorPanel layer={layer} {...spies} {...(extra as object)} />);
  return spies;
}

describe('Inspector, accessories box (designer)', () => {
  it('offers Edit card, Edit footer and Save as accessories template', () => {
    const spies = mount(box());
    fireEvent.click(screen.getByRole('button', { name: 'Edit card' }));
    expect(spies.onEditAccessoryCard).toHaveBeenCalledWith('acc1');
    fireEvent.click(screen.getByRole('button', { name: 'Edit footer' }));
    expect(spies.onEditAccessoryFooter).toHaveBeenCalledWith('acc1');
    fireEvent.click(screen.getByRole('button', { name: 'Save as accessories template' }));
    expect(spies.onSaveAccessoryTemplate).toHaveBeenCalledWith('acc1');
  });

  it('a box with no template link shows no Linked note and no Detach', () => {
    mount(box());
    expect(screen.queryByText(/Linked:/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Detach' })).toBeNull();
  });

  it('a linked box names its template with the used-in count and Detach clears presetId', () => {
    const spies = mount(box({ presetId: 'preset-1' }), {
      accessoryTemplate: { name: 'FREE vertical', usedIn: 3 },
    });
    expect(screen.getByText(/Linked: FREE vertical/)).toBeInTheDocument();
    expect(screen.getByText(/used in 3 tag templates/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Detach' }));
    expect(spies.onUpdateProps).toHaveBeenCalledWith('acc1', expect.objectContaining({ presetId: null }));
  });

  it('says "1 tag template" in the singular', () => {
    mount(box({ presetId: 'preset-1' }), { accessoryTemplate: { name: 'Dealer Kit included', usedIn: 1 } });
    expect(screen.getByText(/used in 1 tag template\b/)).toBeInTheDocument();
  });

  it('Footer note switch turns footer.show on', () => {
    const spies = mount(box());
    const toggle = screen.getByRole('checkbox', { name: 'Footer note' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(spies.onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({ footer: expect.objectContaining({ show: true }) }),
    );
  });

  it('Footer note switch turns an existing footer off and keeps its elements', () => {
    const footer = { show: true, height_mm: 6, elements: [{ id: 'f1', kind: 'text', text: '* Colour follows sink' }] };
    const spies = mount(box({ footer }));
    const toggle = screen.getByRole('checkbox', { name: 'Footer note' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(toggle);
    expect(spies.onUpdateProps).toHaveBeenCalledWith(
      'acc1',
      expect.objectContaining({
        footer: expect.objectContaining({ show: false, elements: footer.elements }),
      }),
    );
  });

  it('shows the fixed shrink minimum, not editable', () => {
    mount(box());
    expect(screen.getByText(/70%/)).toBeInTheDocument();
  });
});

describe('Inspector, a selected card element', () => {
  const edit = (elementId: string) => ({ accessoryEdit: { layerId: 'acc1', target: 'card', elementId } });

  const optionLabels = () =>
    Array.from(screen.getByLabelText('Shows').querySelectorAll('option'))
      .map((o) => o.textContent ?? '')
      .filter(Boolean);

  it('a text element can show Name, Code, Spec lines, Remark or Price, not Picture or Colours', () => {
    mount(box({ card: CARD }), edit('txt'));
    const labels = optionLabels();
    for (const wanted of ['Name', 'Code', 'Spec lines', 'Remark', 'Price']) expect(labels).toContain(wanted);
    expect(labels).not.toContain('Picture');
    expect(labels).not.toContain('Colours');
  });

  it('changing Shows patches the element field', () => {
    const spies = mount(box({ card: CARD }), edit('txt'));
    fireEvent.change(screen.getByLabelText('Shows'), { target: { value: 'spec' } });
    expect(spies.onUpdateAccessoryElement).toHaveBeenCalledWith('txt', expect.objectContaining({ field: 'spec' }));
  });

  it('a picture element shows Picture only', () => {
    mount(box({ card: CARD }), edit('pic'));
    expect(optionLabels()).toEqual(['Picture']);
  });

  it('a colour dots element shows Colours and offers Dot size, Gap and Row / Column', () => {
    const spies = mount(box({ card: CARD }), edit('dots'));
    expect(optionLabels()).toEqual(['Colours']);
    expect(screen.getByLabelText('Dot size (mm)')).toBeInTheDocument();
    expect(screen.getByLabelText('Gap (mm)')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Row' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Column' }));
    expect(spies.onUpdateAccessoryElement).toHaveBeenCalledWith(
      'dots',
      expect.objectContaining({ dotDirection: 'column' }),
    );
  });

  it('the element inspector replaces the box sections while an element is selected', () => {
    mount(box({ card: CARD }), edit('txt'));
    expect(screen.getByLabelText('Shows')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save as accessories template' })).toBeNull();
  });

  it('a hide switch on the element hides it', () => {
    const spies = mount(box({ card: CARD }), edit('txt'));
    fireEvent.click(screen.getByRole('button', { name: 'Hide element' }));
    expect(spies.onUpdateAccessoryElement).toHaveBeenCalledWith('txt', expect.objectContaining({ hidden: true }));
  });
});
