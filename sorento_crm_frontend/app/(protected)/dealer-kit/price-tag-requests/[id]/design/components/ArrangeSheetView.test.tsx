/**
 * AC-S7-6 (PLAN-price-tag-r10.md S7): the Arrange view shows no page, bleed
 * or gap inputs and no drag handle - S7 retired manual arrangement outright,
 * `autoArrange` decides the whole layout - and shows a per-sheet line
 * `<template name> - C x R, used of N`. AC-S7-10's "No tag fits this page"
 * message stays for a size that overflows the page in both rotations.
 *
 * Already wired (`ArrangeSheetView.tsx` reads `placement`/`templateNameById`
 * straight into `sheetLabel`, and the old page/bleed/gap toolbar and drag
 * handling are simply gone from the file), so every test here is a GREEN
 * regression guard - Phase 1 shipped the real markup.
 *
 * `react-konva`/`KonvaTagLayer` are stood in for plain markup, the same
 * pattern `TagCanvasEditor.preview.test.tsx` uses: the Stage/Layer/Group
 * primitives need a real `<canvas>` context jsdom does not provide.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

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
    Text: passthrough('text'),
  };
});

vi.mock(
  '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer',
  () => ({
    KonvaTagLayer: ({ layer }: { layer: TagLayer }) => (
      <div data-testid={`layer-${layer.id}`} />
    ),
  }),
);

import { ArrangeSheetView } from './ArrangeSheetView';
import type { PlacedTag, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import type { SheetPlacement } from '@/lib/dealer-kit/request-tags';

function placedTag(id: string, requestTagId: string): PlacedTag {
  return {
    id,
    template_id: 'tpl-small',
    request_tag_id: requestTagId,
    x_mm: 5,
    y_mm: 5,
    width_mm: 66.7,
    height_mm: 31.9,
    layers: [],
  };
}

function doc(sheets: TagSheetDoc['sheets']): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'auto', page_width_mm: 210, page_height_mm: 297, bleed_mm: 5, gap_mm: 0 },
    sheets,
  };
}

const NOOP = () => {};

function baseProps() {
  return {
    activeSheetIndex: 0,
    onActiveSheetChange: NOOP,
    zoom: 1,
    onZoomChange: NOOP,
    selectedTagId: null,
    onSelectTag: NOOP,
    resolved: new Map(),
    assetUrls: {},
    onPrintSheet: NOOP,
    printing: false,
    templateNameById: { 'tpl-small': 'Small Price Tag SP' },
  };
}

describe('ArrangeSheetView (AC-S7-6)', () => {
  it('shows no page, bleed or gap inputs anywhere', () => {
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-small', width_mm: 66.7, height_mm: 31.9, rotation: 0, cols: 3, rows: 9, capacity: 27 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        doc={doc([{ id: 'sheet-1', tags: [placedTag('a-c0', 'l1')] }])}
        placement={placement}
      />,
    );

    expect(screen.queryByLabelText(/bleed/i)).toBeNull();
    expect(screen.queryByLabelText(/gap/i)).toBeNull();
    expect(screen.queryByLabelText(/page width/i)).toBeNull();
    expect(screen.queryByLabelText(/page height/i)).toBeNull();
    expect(screen.queryByRole('spinbutton')).toBeNull();
  });

  it('renders no drag handle - the layer is read-only, not draggable', () => {
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-small', width_mm: 66.7, height_mm: 31.9, rotation: 0, cols: 3, rows: 9, capacity: 27 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        doc={doc([{ id: 'sheet-1', tags: [placedTag('a-c0', 'l1')] }])}
        placement={placement}
      />,
    );

    expect(screen.queryByLabelText(/drag/i)).toBeNull();
    expect(screen.queryByTitle(/drag/i)).toBeNull();
  });

  it('AC-S7-6: the per-sheet line reads "<template name> - C x R, used of N"', () => {
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-small', width_mm: 66.7, height_mm: 31.9, rotation: 0, cols: 3, rows: 9, capacity: 27 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        doc={doc([
          {
            id: 'sheet-1',
            tags: Array.from({ length: 27 }, (_, i) => placedTag(`a-c${i}`, 'l1')),
          },
        ])}
        placement={placement}
      />,
    );

    expect(
      screen.getByTitle('Small Price Tag SP - 3 x 9, 27 of 27'),
    ).toBeInTheDocument();
  });

  it('AC-S7-10: capacity 0 shows "No tag fits this page" and draws no sheet', () => {
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-big', width_mm: 400, height_mm: 400, rotation: 0, cols: 0, rows: 0, capacity: 0 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        doc={doc([{ id: 'sheet-1', tags: [placedTag('a-c0', 'l1')] }])}
        placement={placement}
        templateNameById={{ 'tpl-big': 'Oversized' }}
      />,
    );

    expect(screen.getByText('No tag fits this page')).toBeInTheDocument();
    expect(screen.queryByText('[data-konva="stage"]')).toBeNull();
    expect(document.querySelector('[data-konva="stage"]')).toBeNull();
  });
});
