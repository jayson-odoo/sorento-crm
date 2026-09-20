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
    function KonvaStandIn({
      children,
      onClick,
      onTap,
      stroke,
    }: {
      children?: React.ReactNode;
      onClick?: (e: unknown) => void;
      onTap?: (e: unknown) => void;
      stroke?: string;
    }) {
      return (
        <div
          data-konva={name}
          data-stroke={stroke}
          onClick={
            onClick
              ? (domEvent: { stopPropagation: () => void }) => {
                  // Real DOM stopPropagation so a click on an inner Group
                  // never bubbles up to the Stage's own onClick (which
                  // expects a real Konva event with `.getStage()`).
                  domEvent.stopPropagation();
                  onClick({ cancelBubble: false });
                }
              : undefined
          }
        >
          {children}
        </div>
      );
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

// ---------------------------------------------------------------------------
// AC-S10-3 second half (captain's ruling, phase 3 review): selection on the
// arrange sheet is keyed by REQUEST tag id, not the placed copy's own
// `-c0`/`-c1` id - `TagOnCanvas` currently compares/reports `tag.id` (the
// copy) instead of `tag.request_tag_id`.
// ---------------------------------------------------------------------------

describe('ArrangeSheetView - selection by request tag id (AC-S10-3)', () => {
  it('marks the placed copy whose request_tag_id matches selectedTagId as selected', () => {
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-small', width_mm: 66.7, height_mm: 31.9, rotation: 0, cols: 3, rows: 9, capacity: 27 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        doc={doc([
          { id: 'sheet-1', tags: [_placedFor('req-tag-a'), _placedFor('req-tag-b')] },
        ])}
        placement={placement}
        selectedTagId="req-tag-b"
      />,
    );

    const groups = document.querySelectorAll('[data-konva="group"]');
    expect(groups).toHaveLength(2);
    const rects = Array.from(groups).map((g) => g.querySelector('[data-konva="rect"]'));
    expect(rects[0]?.getAttribute('data-stroke')).toBe('#d4d4d8');
    expect(rects[1]?.getAttribute('data-stroke')).toBe('#3b82f6');
  });

  it('clicking a placed copy calls onSelectTag with the REQUEST tag id, not the copy id', () => {
    const onSelectTag = vi.fn();
    const placement: SheetPlacement[] = [
      { template_id: 'tpl-small', width_mm: 66.7, height_mm: 31.9, rotation: 0, cols: 3, rows: 9, capacity: 27 },
    ];
    render(
      <ArrangeSheetView
        {...baseProps()}
        onSelectTag={onSelectTag}
        doc={doc([{ id: 'sheet-1', tags: [_placedFor('req-tag-a')] }])}
        placement={placement}
      />,
    );

    const group = document.querySelector('[data-konva="group"]') as HTMLElement;
    group.click();

    expect(onSelectTag).toHaveBeenCalledWith('req-tag-a');
    expect(onSelectTag).not.toHaveBeenCalledWith('req-tag-a-c0');
  });
});

function _placedFor(requestTagId: string): PlacedTag {
  return placedTag(`${requestTagId}-c0`, requestTagId);
}
