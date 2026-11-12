'use client';

import * as React from 'react';

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { cn } from '@/lib/utils';
import {
  boxToStyle,
  moveBox,
  rectFromDrag,
  resizeBox,
  type Corner,
  type PageBox,
} from './box-geometry';

const CORNERS: { corner: Corner; className: string; cursor: string }[] = [
  { corner: 'nw', className: '-left-1.5 -top-1.5', cursor: 'cursor-nwse-resize' },
  { corner: 'ne', className: '-right-1.5 -top-1.5', cursor: 'cursor-nesw-resize' },
  { corner: 'sw', className: '-bottom-1.5 -left-1.5', cursor: 'cursor-nesw-resize' },
  { corner: 'se', className: '-bottom-1.5 -right-1.5', cursor: 'cursor-nwse-resize' },
];

/** Smallest box a drag may leave behind: a click is not a box. */
const MIN_DRAW_W = 0.01;
const MIN_DRAW_H = 0.004;

type Gesture =
  | { kind: 'move'; index: number; startX: number; startY: number; origin: PageBox }
  | { kind: 'resize'; index: number; corner: Corner; startX: number; startY: number; origin: PageBox };

/**
 * The boxes of one PDF page, drawn on top of its text layer as percentages of the page so they
 * follow any zoom. `boxes` is the WHOLE list (indices are global); only this page's are drawn.
 * Draw mode turns the page into a drag surface; a box moves by its body and resizes by a corner.
 * A box is deleted by selecting it and pressing Delete/Backspace, or from its right-click menu
 * (CERT-TAB-UX: no separate Remove button). `flashed` outlines one box briefly after "Go to box".
 */
export function BoxOverlay({
  pageNumber,
  boxes,
  editable,
  drawing,
  selected,
  flashed = null,
  drawProductId = null,
  onSelect,
  onChange,
  onRemove,
}: {
  pageNumber: number;
  boxes: PageBox[];
  editable: boolean;
  drawing: boolean;
  selected: number | null;
  /** The box "Go to box" just jumped to; outlined until the caller clears it. */
  flashed?: number | null;
  drawProductId?: string | null;
  onSelect: (index: number | null) => void;
  onChange: (boxes: PageBox[]) => void;
  onRemove: (index: number) => void;
}) {
  const hostRef = React.useRef<HTMLDivElement>(null);
  const gesture = React.useRef<Gesture | null>(null);
  const boxesRef = React.useRef(boxes);
  boxesRef.current = boxes;
  const [draft, setDraft] = React.useState<{ a: { x: number; y: number }; b: { x: number; y: number } } | null>(null);

  const size = () => {
    const rect = hostRef.current?.getBoundingClientRect();
    return { rect, width: rect?.width || 1, height: rect?.height || 1 };
  };

  const startDraw = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawing || !editable) return;
    const { rect } = size();
    if (!rect) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    setDraft({ a: point, b: point });
  };

  const moveDraw = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!draft) return;
    const { rect } = size();
    if (!rect) return;
    setDraft({ a: draft.a, b: { x: event.clientX - rect.left, y: event.clientY - rect.top } });
  };

  const endDraw = () => {
    if (!draft) return;
    const { width, height } = size();
    const r = rectFromDrag(draft.a, draft.b, { width, height });
    setDraft(null);
    if (r.w < MIN_DRAW_W || r.h < MIN_DRAW_H) return;
    const next = [...boxesRef.current, { page: pageNumber, ...r, product_id: drawProductId }];
    onChange(next);
    onSelect(next.length - 1);
  };

  const beginGesture = (event: React.PointerEvent, next: Gesture) => {
    event.stopPropagation();
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    gesture.current = next;
    onSelect(next.index);
  };

  const onGestureMove = (event: React.PointerEvent) => {
    const g = gesture.current;
    if (!g) return;
    const { width, height } = size();
    const dx = (event.clientX - g.startX) / width;
    const dy = (event.clientY - g.startY) / height;
    const updated = g.kind === 'move' ? moveBox(g.origin, dx, dy) : resizeBox(g.origin, g.corner, dx, dy);
    onChange(boxesRef.current.map((b, i) => (i === g.index ? updated : b)));
  };

  const endGesture = () => {
    gesture.current = null;
  };

  const draftStyle = draft
    ? (() => {
        const { width, height } = size();
        return boxToStyle(rectFromDrag(draft.a, draft.b, { width, height }));
      })()
    : null;

  return (
    <div
      ref={hostRef}
      data-testid={`box-overlay-${pageNumber}`}
      className={cn(
        'absolute inset-0 z-10',
        drawing && editable ? 'cursor-crosshair touch-none' : 'pointer-events-none',
      )}
      onPointerDown={startDraw}
      onPointerMove={moveDraw}
      onPointerUp={endDraw}
    >
      {boxes.map((box, index) => {
        if (box.page !== pageNumber) return null;
        const element = (
          <div
            key={index}
            role="group"
            aria-label="Box"
            tabIndex={editable ? 0 : -1}
            data-box-index={index}
            data-selected={selected === index || undefined}
            data-flashed={flashed === index || undefined}
            className={cn(
              'absolute border-2 border-rose-600 bg-rose-500/10',
              editable && !drawing && 'pointer-events-auto cursor-move touch-none',
              selected === index && 'ring-2 ring-primary/60',
              // Static, no animation: it follows a keyboard action and must respect reduced motion.
              flashed === index && 'ring-4 ring-warning',
            )}
            style={boxToStyle(box)}
            onPointerDown={(event) => {
              if (!editable || drawing || event.button !== 0) return;
              beginGesture(event, { kind: 'move', index, startX: event.clientX, startY: event.clientY, origin: box });
            }}
            onPointerMove={onGestureMove}
            onPointerUp={endGesture}
            onContextMenu={() => onSelect(index)}
            onKeyDown={(event) => {
              if (!editable) return;
              if (event.key === 'Delete' || event.key === 'Backspace') {
                event.preventDefault();
                event.stopPropagation();
                onRemove(index);
              }
            }}
          >
            {editable && !drawing && selected === index &&
              CORNERS.map(({ corner, className, cursor }) => (
                <span
                  key={corner}
                  data-corner={corner}
                  className={cn('pointer-events-auto absolute size-3 rounded-sm border border-rose-600 bg-white', className, cursor)}
                  onPointerDown={(event) =>
                    beginGesture(event, {
                      kind: 'resize',
                      index,
                      corner,
                      startX: event.clientX,
                      startY: event.clientY,
                      origin: box,
                    })
                  }
                  onPointerMove={onGestureMove}
                  onPointerUp={endGesture}
                />
              ))}
          </div>
        );
        if (!editable || drawing) return element;
        return (
          <ContextMenu key={index}>
            <ContextMenuTrigger asChild>{element}</ContextMenuTrigger>
            <ContextMenuContent>
              <ContextMenuItem variant="destructive" onSelect={() => onRemove(index)}>
                Delete
                <ContextMenuShortcut>Del</ContextMenuShortcut>
              </ContextMenuItem>
            </ContextMenuContent>
          </ContextMenu>
        );
      })}
      {draftStyle && (
        <div className="absolute border-2 border-dashed border-rose-600 bg-rose-500/10" style={draftStyle} />
      )}
    </div>
  );
}
