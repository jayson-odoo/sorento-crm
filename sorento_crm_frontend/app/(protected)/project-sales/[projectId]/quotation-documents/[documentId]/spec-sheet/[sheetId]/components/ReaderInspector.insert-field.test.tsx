/**
 * SPEC-SHEET-DESIGNER-PARITY (owner hand test #2331): the spec sheet page's own Inspector offers
 * Insert field.
 * ReaderInspector passes `onInsertField` to InspectorPanel; the button opens InsertFieldDialog
 * (the full registry: `{{doc.*}}`, `{{line.*}}`, product fields) and Done writes the content into the selected text layer through the
 * embedded controller. Written test-FIRST.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings', () => ({
  useKitLibrary: () => ({ assetUrls: {}, thumbUrls: {}, fonts: [], specKeys: [], fontOptions: [] }),
}));
// The inspector renders Insert field only when it is handed the callback, as the real one does.
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/InspectorPanel', () => ({
  InspectorPanel: ({ onInsertField }: { onInsertField?: () => void }) => (
    <div data-testid="inspector">
      {onInsertField && (
        <button type="button" onClick={onInsertField}>
          Insert field
        </button>
      )}
    </div>
  ),
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { ReaderInspector } from './ReaderInspector';

const LAYER = {
  id: 'title',
  type: 'text',
  x_mm: 0,
  y_mm: 0,
  width_mm: 50,
  height_mm: 10,
  rotation_deg: 0,
  z_index: 1,
  visible: true,
  props: { kind: 'text', text: 'Re: ', fontFamily: 'DM Sans', fontSize: 12, color: '#000', align: 'left' },
} as unknown as TagLayer;

function mount(layer: TagLayer = LAYER) {
  const controller = { updateLayer: vi.fn(), updateLayerProps: vi.fn() };
  render(
    <ReaderInspector
      pageKey="k1"
      layer={layer}
      layers={[layer]}
      controller={controller as never}
      mode="page"
      onModeChange={vi.fn()}
      onApplyAll={vi.fn()}
    />,
  );
  return controller;
}

describe('Insert field on the spec sheet page Inspector', () => {
  it('is offered, opens the dialog with doc fields searchable', () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'doc.project' } });
    expect(screen.getByText('Project title')).toBeInTheDocument();
  });

  it('Done writes the content into the selected text layer through the controller', () => {
    const controller = mount();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'doc.project' } });
    fireEvent.click(screen.getByText('Project title'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(controller.updateLayerProps).toHaveBeenCalledTimes(1);
    const [id, changes] = controller.updateLayerProps.mock.calls[0];
    expect(id).toBe('title');
    expect((changes as { text: string }).text).toContain('{{doc.project_title}}');
    expect((changes as { text: string }).text.startsWith('Re: ')).toBe(true);
  });

  it('offers line and product fields too (Area, Description)', () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'line.area' } });
    expect(screen.getByText('Area')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'product.description' } });
    expect(screen.getByText('Description')).toBeInTheDocument();
  });

  it('a layer showing its text override gets the override, where the text is drawn from', () => {
    const bound = { ...LAYER, text_override: 'AREA : ' } as TagLayer;
    const controller = mount(bound);
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'line.area' } });
    fireEvent.click(screen.getByText('Area'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(controller.updateLayerProps).not.toHaveBeenCalled();
    expect(controller.updateLayer).toHaveBeenCalledWith('title', {
      text_override: expect.stringContaining('{{line.area}}'),
    });
  });

  it('offers the slice B document fields too (Subject title)', () => {
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Insert field' }));
    fireEvent.change(screen.getByPlaceholderText('Search fields...'), { target: { value: 'doc.subject' } });
    expect(screen.getByText('Subject title')).toBeInTheDocument();
  });
});
