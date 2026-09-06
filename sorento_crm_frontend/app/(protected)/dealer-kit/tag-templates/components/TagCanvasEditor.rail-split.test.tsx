/**
 * The TAG SIZE / LAYERS divider survives a line change (S7, GitHub #676).
 *
 * `RequestTagDesigner` remounts `TagCanvasEditor` with a new `key` on every
 * line change, and `react-resizable-panels` only reads a Panel's
 * `defaultSize` ONCE, at mount - before hydration has replaced the default
 * `railSplit` with what is stored, and before the group's real height is
 * known (`panelGroupSize` starts at `{0, 0}`). Nothing tells the panel to
 * move once those real values arrive a render later, so the stored split
 * round-tripped through localStorage without ever being applied.
 *
 * `react-resizable-panels` needs a real layout engine jsdom does not have, so
 * `@/components/ui/resizable` is stood in for by plain divs whose `Panel`
 * exposes an imperative `resize` the test can assert on - the same
 * `KonvaTagLayer`/`react-konva` stand-in pattern the sibling test files use,
 * one layer up the tree. The global `ResizeObserver` stub every test gets
 * (`vitest.setup.ts`) never calls back, so this file swaps in one that does,
 * to stand in for the real group being measured.
 */

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_PANEL_LAYOUT,
  writePanelLayout,
} from '@/lib/dealer-kit/canvas-panels';
import type { TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

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
  KonvaTagLayer: () => null,
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

/** What the "canvas-left-rail" Panel's imperative `resize` records. */
const rail = vi.hoisted(() => ({ resize: vi.fn() }));

vi.mock('@/components/ui/resizable', async () => {
  const React = await import('react');

  const ResizablePanelGroup = ({
    children,
    className,
  }: {
    children?: React.ReactNode;
    className?: string;
  }) => <div className={className}>{children}</div>;

  interface PanelStandInProps {
    id?: string;
    className?: string;
    children?: React.ReactNode;
  }

  const ResizablePanel = React.forwardRef<
    { resize: (size: number) => void },
    PanelStandInProps
  >(function ResizablePanelStandIn(props, ref) {
    React.useImperativeHandle(ref, () => ({
      resize: props.id === 'canvas-left-rail' ? rail.resize : () => {},
      collapse: () => {},
      expand: () => {},
      getSize: () => 0,
      isCollapsed: () => false,
      isExpanded: () => true,
    }));
    return (
      <div data-panel-id={props.id} className={props.className}>
        {props.children}
      </div>
    );
  });

  const ResizableHandle = () => <div />;

  return { ResizablePanelGroup, ResizablePanel, ResizableHandle };
});

import { TagCanvasEditor } from './TagCanvasEditor';

// -- A ResizeObserver that actually calls back ------------------------------

type RoEntry = { contentRect: { width: number; height: number } };
let roCallback: ((entries: RoEntry[]) => void) | null = null;

class FakeResizeObserver {
  constructor(cb: (entries: RoEntry[]) => void) {
    roCallback = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

function reportGroupHeight(height: number) {
  act(() => {
    roCallback?.([{ contentRect: { width: 1200, height } }]);
  });
}

function emptyDoc(): TagTemplateDoc {
  return { width_mm: 60, height_mm: 40, layers: [] };
}

describe('TagCanvasEditor rail split persistence (S7, GitHub #676)', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    roCallback = null;
    rail.resize.mockClear();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('applies the stored split once the group is actually measured', () => {
    writePanelLayout({ ...DEFAULT_PANEL_LAYOUT, railSplit: 300 });

    render(
      <TagCanvasEditor doc={emptyDoc()} onChange={vi.fn()} leftRail={<div>Tag Size</div>} />,
    );

    // Nothing to apply yet: the group has not been measured (height still 0).
    expect(rail.resize).not.toHaveBeenCalled();

    reportGroupHeight(600);

    // 300 / 600 = 50%.
    expect(rail.resize).toHaveBeenCalledWith(50);
  });

  it('does not fight a later ResizeObserver tick once applied', () => {
    writePanelLayout({ ...DEFAULT_PANEL_LAYOUT, railSplit: 300 });

    render(
      <TagCanvasEditor doc={emptyDoc()} onChange={vi.fn()} leftRail={<div>Tag Size</div>} />,
    );
    reportGroupHeight(600);
    expect(rail.resize).toHaveBeenCalledTimes(1);

    rail.resize.mockClear();
    reportGroupHeight(900);

    expect(rail.resize).not.toHaveBeenCalled();
  });

  it('re-applies after a remount, the same way a line change remounts the editor', () => {
    writePanelLayout({ ...DEFAULT_PANEL_LAYOUT, railSplit: 300 });

    const { rerender } = render(
      <TagCanvasEditor
        key="line-1"
        doc={emptyDoc()}
        onChange={vi.fn()}
        leftRail={<div>Tag Size</div>}
      />,
    );
    reportGroupHeight(600);
    expect(rail.resize).toHaveBeenCalledWith(50);

    rail.resize.mockClear();
    rerender(
      <TagCanvasEditor
        key="line-2"
        doc={emptyDoc()}
        onChange={vi.fn()}
        leftRail={<div>Tag Size</div>}
      />,
    );
    reportGroupHeight(600);

    expect(rail.resize).toHaveBeenCalledWith(50);
  });
});
