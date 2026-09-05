/**
 * Inline text edit through the editor itself (S2, D5) - specifically the
 * integration bug S1 caught: `commitInlineEdit` used to target whatever
 * layer was CURRENTLY selected rather than the layer the editor was opened
 * on, and clicking a different text layer while editing raced the textarea's
 * own blur. The pure commit-vs-cancel decision is pinned at the unit level
 * in `InlineTextEditor.test.tsx` (B2); this is the wiring: clicking a
 * DIFFERENT text layer while editing commits what was typed into the layer
 * that was actually being edited, never into the newly-selected one, and
 * never gets silently discarded (AC-S2-2 "clicking outside commits").
 *
 * Konva does not run in jsdom - same stand-in pattern as
 * `TagCanvasEditor.preview.test.tsx`.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  LineTagData,
  TagBindingData,
  TagLayer,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

// -- Stand-ins for everything that needs a browser or a server ---------------

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    display,
    onSelect,
    onDoubleClick,
  }: {
    layer: TagLayer;
    display?: { text?: string };
    onSelect?: (id: string, additive: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      onClick={() => onSelect?.(layer.id, false)}
      onDoubleClick={() => onDoubleClick?.(layer.id)}
    >
      {display?.text ?? ''}
    </div>
  ),
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

// -- The document under test -------------------------------------------------

function textLayer(id: string, text: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 20,
    height_mm: 6,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text },
  };
}

function twoLooseTextLayersDoc(): TagTemplateDoc {
  return {
    width_mm: 60,
    height_mm: 40,
    layers: [textLayer('a', 'Original A'), textLayer('b', 'Original B')],
  };
}

describe('TagCanvasEditor inline edit - clicking a different layer (S1, AC-S2-2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('commits the typed text into the layer being edited, not the newly selected one', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />);

    fireEvent.doubleClick(screen.getByTestId('layer-a'));
    const editor = await screen.findByTestId('inline-text-editor');
    fireEvent.change(editor, { target: { value: 'Edited A' } });

    // Clicking a DIFFERENT text layer while still editing - this used to
    // either discard the edit or write it onto layer b.
    fireEvent.click(screen.getByTestId('layer-b'));

    await waitFor(() =>
      expect(screen.getByTestId('layer-a')).toHaveTextContent('Edited A'),
    );
    expect(screen.getByTestId('layer-b')).toHaveTextContent('Original B');
    expect(screen.queryByTestId('inline-text-editor')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedA = saved.layers.find((l) => l.id === 'a');
    const savedB = saved.layers.find((l) => l.id === 'b');
    expect(savedA?.props.kind === 'text' ? savedA.props.text : null).toBe('Edited A');
    expect(savedB?.props.kind === 'text' ? savedB.props.text : null).toBe('Original B');
  });

  it('does not write anything when the selection moves away without typing (B2)', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />);

    fireEvent.doubleClick(screen.getByTestId('layer-a'));
    await screen.findByTestId('inline-text-editor');

    fireEvent.click(screen.getByTestId('layer-b'));

    await waitFor(() => expect(screen.queryByTestId('inline-text-editor')).toBeNull());
    expect(screen.getByTestId('layer-a')).toHaveTextContent('Original A');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedA = saved.layers.find((l) => l.id === 'a');
    expect(savedA?.props.kind === 'text' ? savedA.props.text : null).toBe('Original A');
  });
});

// ---------------------------------------------------------------------------
// A sole-token layer opens on its RESOLVED value (S3, AC-S3-1/S3-2/S3-4).
// ---------------------------------------------------------------------------

function lineTagData(overrides: Partial<LineTagData> = {}): LineTagData {
  return {
    line_id: 'line-1',
    code: 'SRTWT8267-GM',
    name: 'Kitchen Sink',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: 'Stainless steel',
    specs: [],
    set_members: '',
    images: [],
    list_price: 1599,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    ...overrides,
  };
}

const LINE_BOUND_DATA: TagBindingData = { kind: 'line', line: lineTagData() };

/** A slot-bound layer whose override holds a merge field (D57, AC-S3-5). */
function boundTokenLayer(id: string, override: string): TagLayer {
  return {
    ...textLayer(id, 'placeholder'),
    slot_binding: 'code',
    text_override: override,
  };
}

function docWithLayers(layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers };
}

describe('TagCanvasEditor inline edit - sole-token layer opens resolved (S3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens a whole-token layer on the resolved code, fully selected (AC-S3-1)', async () => {
    const doc = docWithLayers([textLayer('code', '{{product.code}}')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-code'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('SRTWT8267-GM');
    expect(editor).toHaveAttribute('readonly');
    expect(editor.selectionStart).toBe(0);
    expect(editor.selectionEnd).toBe('SRTWT8267-GM'.length);
  });

  it('typing does nothing, and Escape/blur leave the layer text as the token (AC-S3-2)', async () => {
    const onChange = vi.fn();
    const doc = docWithLayers([textLayer('code', '{{product.code}}')]);
    render(<TagCanvasEditor doc={doc} onChange={onChange} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-code'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    fireEvent.change(editor, { target: { value: 'typed over it' } });
    expect(editor.value).toBe('SRTWT8267-GM');

    fireEvent.keyDown(editor, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByTestId('inline-text-editor')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedLayer = saved.layers.find((l) => l.id === 'code');
    expect(savedLayer?.props.kind === 'text' ? savedLayer.props.text : null).toBe(
      '{{product.code}}',
    );
  });

  it('a layer with mixed text still opens raw and editable (AC-S3-3)', async () => {
    const doc = docWithLayers([textLayer('mixed', 'Code {{product.code}}')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-mixed'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('Code {{product.code}}');
    expect(editor).not.toHaveAttribute('readonly');
  });

  it('a plain text layer still opens raw and editable (AC-S3-3)', async () => {
    const doc = docWithLayers([textLayer('plain', 'Plain words')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-plain'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('Plain words');
    expect(editor).not.toHaveAttribute('readonly');
  });

  it('opens a BOUND layer typed over with a token on the resolved code too (AC-S3-5)', async () => {
    // The seeded product block's code layer: bound to the `code` slot AND
    // holding `{{product.code}}` as its override (D57 - a bound layer typed
    // over with a merge field keeps following the product). The first cut of
    // S3 excluded every bound layer, so the one layer a user actually
    // double-clicks to copy a code still opened on the braces.
    const doc = docWithLayers([boundTokenLayer('code', '{{product.code}}')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-code'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('SRTWT8267-GM');
    expect(editor).toHaveAttribute('readonly');
  });

  it('opens on the TRIMMED value when the token is padded with whitespace (AC-S3-5)', async () => {
    const doc = docWithLayers([boundTokenLayer('code', ' {{product.code}} ')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} boundData={LINE_BOUND_DATA} />);

    fireEvent.doubleClick(screen.getByTestId('layer-code'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('SRTWT8267-GM');
  });

  it('with no bound data (template editor, no preview), a sole-token layer opens raw (AC-S3-4)', async () => {
    const doc = docWithLayers([textLayer('code', '{{product.code}}')]);
    render(<TagCanvasEditor doc={doc} onChange={vi.fn()} />);

    fireEvent.doubleClick(screen.getByTestId('layer-code'));
    const editor = (await screen.findByTestId(
      'inline-text-editor',
    )) as HTMLTextAreaElement;

    expect(editor.value).toBe('{{product.code}}');
    expect(editor).not.toHaveAttribute('readonly');
  });
});
