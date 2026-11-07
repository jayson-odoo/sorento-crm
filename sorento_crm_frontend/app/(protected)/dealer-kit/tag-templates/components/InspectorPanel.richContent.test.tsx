/**
 * PRICETAG-COMBO-FORMAT fix round 1, R8: the designer's Content box for a layer bound to a
 * description slot shows the resolved description as plain text and is read-only (the description
 * is edited on the product / combo page, never as raw markup here).
 *
 * Written test-FIRST: today the box shows the HTML and is editable.
 */
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({ SearchableSelect: () => <div data-testid="select" /> }));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const HTML = '<p><strong>SRTBF11416</strong> (CABINET)</p><p>L400xW345xH390mm</p>';

function layer(slot: string | null): TagLayer {
  return {
    id: 't1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: slot,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
    },
  } as TagLayer;
}

function contentBox(slot: string | null, resolvedText: string | null = HTML) {
  const { container } = render(
    <InspectorPanel
      layer={layer(slot)}
      onUpdate={vi.fn()}
      onUpdateProps={vi.fn()}
      resolvedText={resolvedText}
    />,
  );
  return container.querySelector('textarea') as HTMLTextAreaElement;
}

describe('Content box for a description-bound layer (R8)', () => {
  for (const slot of ['combo_description', 'price_tag_description']) {
    it(`R8: ${slot} shows plain text, read-only`, () => {
      const box = contentBox(slot);
      expect(box.value).toBe('SRTBF11416 (CABINET)\nL400xW345xH390mm');
      expect(box.readOnly).toBe(true);
    });
  }

  // DESIGNER-RICH-TEXT: any other layer's Content box is the editable rich editor (its own
  // suite is InspectorPanel.richContentEditor.test.tsx).
  it('R8: any other layer keeps an editable Content box with its own text', async () => {
    const { container } = render(
      <InspectorPanel layer={layer(null)} onUpdate={vi.fn()} onUpdateProps={vi.fn()} resolvedText={HTML} />,
    );
    expect(container.querySelector('textarea')).toBeNull();
    const box = await waitFor(() => {
      const el = container.querySelector<HTMLElement>('.ProseMirror');
      expect(el).not.toBeNull();
      return el!;
    });
    expect(box.textContent).toBe('Hello');
    expect(box.getAttribute('contenteditable')).toBe('true');
  });
});
