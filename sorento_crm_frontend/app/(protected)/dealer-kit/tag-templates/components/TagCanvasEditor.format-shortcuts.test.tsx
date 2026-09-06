/**
 * Cmd+B/I/U/Shift+X are scoped to the inline editor, not every input (N2).
 *
 * The window keydown handler answers these shortcuts AHEAD of the `isInput`
 * guard so they work while the inline text editor - itself a textarea - has
 * focus (AC-S2-4). That exception used to apply unconditionally, so Cmd+B
 * while typing a name in an UNRELATED input (the "Save as template" dialog,
 * a layer's own X/Y field, ...) bolded the canvas underneath it instead of
 * typing a B. Scoped to `editingLayerId` specifically.
 *
 * Konva does not run in jsdom - same stand-in pattern as
 * `TagCanvasEditor.preview.test.tsx`.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
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

describe('TagCanvasEditor keyboard shortcuts - scoped to the inline editor (N2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('Cmd+B while typing in an UNRELATED input (e.g. "Save as template" name) types a B, does not bold the canvas', async () => {
    const onChange = vi.fn();
    render(
      <div>
        <input data-testid="template-name-input" />
        <TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />
      </div>,
    );

    fireEvent.click(screen.getByTestId('layer-a'));
    const nameInput = screen.getByTestId('template-name-input');
    nameInput.focus();
    fireEvent.keyDown(nameInput, { key: 'b', metaKey: true, bubbles: true });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedA = saved.layers.find((l) => l.id === 'a');
    expect(savedA?.props.kind === 'text' ? savedA.props.fontWeight : null).toBe(400);
  });

  it('Cmd+B with the canvas itself in focus still bolds the selected layer', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />);

    fireEvent.click(screen.getByTestId('layer-a'));
    fireEvent.keyDown(document.body, { key: 'b', metaKey: true, bubbles: true });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    const savedA = saved.layers.find((l) => l.id === 'a');
    expect(savedA?.props.kind === 'text' ? savedA.props.fontWeight : null).toBe(700);
  });
});

describe('Ctrl+A / Delete are guarded by document.activeElement, not just e.target (r4c)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * The listener is on `window`, so a keydown that bubbles up carries
   * whatever DOM node it was dispatched on as `e.target` - which is not
   * necessarily the element that actually has focus. Dispatching straight on
   * `window` (rather than on the focused input, the way a real keypress
   * would target it) is what used to slip past the old guard: `e.target`
   * was neither an input nor a textarea, so `isInput` read false even while
   * an unrelated form control had focus.
   */
  it('Ctrl+A while an input has focus does not select every layer', () => {
    const onChange = vi.fn();
    render(
      <div>
        <input data-testid="unrelated-input" />
        <TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />
      </div>,
    );

    const input = screen.getByTestId('unrelated-input');
    input.focus();
    expect(document.activeElement).toBe(input);

    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();

    fireEvent.keyDown(window, { key: 'a', ctrlKey: true, bubbles: true });

    // Nothing got selected: the Delete toolbar action is still disabled.
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();
  });

  it('Ctrl+A still selects every layer when nothing else has focus', () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />);

    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();

    fireEvent.keyDown(window, { key: 'a', ctrlKey: true, bubbles: true });

    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled();
  });

  it('Delete while an input has focus does not delete the selected layer', () => {
    const onChange = vi.fn();
    render(
      <div>
        <input data-testid="unrelated-input" />
        <TagCanvasEditor doc={twoLooseTextLayersDoc()} onChange={onChange} />
      </div>,
    );

    fireEvent.click(screen.getByTestId('layer-a'));
    screen.getByTestId('unrelated-input').focus();

    fireEvent.keyDown(window, { key: 'Delete', bubbles: true });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls.at(-1)?.[0] as TagTemplateDoc;
    expect(saved.layers.map((l) => l.id)).toEqual(['a', 'b']);
  });
});
