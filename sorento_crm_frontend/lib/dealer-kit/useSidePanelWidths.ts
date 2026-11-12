'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';

import {
  DEFAULT_PANEL_LAYOUT,
  LEFT_MAX_PX,
  LEFT_MIN_PX,
  RIGHT_MAX_PX,
  RIGHT_MIN_PX,
  clampLeft,
  clampRight,
  readPanelLayout,
  writePanelLayout,
} from './canvas-panels';

/**
 * Resizable left / right side panels for a designer that hosts its own `ResizablePanelGroup`
 * (`components/ui/resizable`), with the widths the price tag template designer keeps
 * (`TagCanvasEditor`, S1 / D7): the same pixel widths, limits and localStorage key
 * (`canvas-panels.ts`), so a width dragged in one designer is the width in the other
 * (SPEC-SHEET-DESIGNER-PARITY). Only `left` / `right` are touched here; the template designer's
 * own collapse flags and rail split are carried through untouched.
 *
 * Mirrors the template designer's two rules: widths are stored in px and converted to the
 * group's percentages against its measured width, and only a resize that comes from a drag is
 * persisted (the library also reports its own corrections while it measures).
 */
export function useSidePanelWidths() {
  // A callback ref: the host may render a loading state first, so the group mounts later.
  const [groupNode, setGroupNode] = useState<HTMLDivElement | null>(null);
  const groupRef = useCallback((node: HTMLDivElement | null) => setGroupNode(node), []);
  const leftRef = useRef<ImperativePanelHandle>(null);
  const rightRef = useRef<ImperativePanelHandle>(null);
  const [widths, setWidths] = useState({
    left: DEFAULT_PANEL_LAYOUT.left,
    right: DEFAULT_PANEL_LAYOUT.right,
  });
  const [groupWidth, setGroupWidth] = useState(0);
  const dragging = useRef(false);
  const hydrated = useRef(false);
  const applied = useRef(false);

  // Hydrate after mount (server and first paint use the default, as the template designer does).
  useEffect(() => {
    const stored = readPanelLayout();
    setWidths({ left: stored.left, right: stored.right });
    hydrated.current = true;
  }, []);

  useEffect(() => {
    const node = groupNode;
    if (!node) return;
    const measure = () => setGroupWidth(node.clientWidth);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [groupNode]);

  // jsdom never measures; a fixed fallback keeps the percentages sane there and on first paint.
  const width = groupWidth || 1200;
  const pct = (px: number) => (px / width) * 100;

  // `defaultSize` is read once, at mount: once the stored widths AND a real width are known,
  // move the panels there once, so a drag in progress is never fought.
  useEffect(() => {
    if (applied.current || !hydrated.current || groupWidth <= 0) return;
    applied.current = true;
    leftRef.current?.resize((widths.left / groupWidth) * 100);
    rightRef.current?.resize((widths.right / groupWidth) * 100);
  }, [groupWidth, widths]);

  const persist = useCallback((side: 'left' | 'right', px: number) => {
    const value = side === 'left' ? clampLeft(px) : clampRight(px);
    setWidths((prev) => ({ ...prev, [side]: value }));
    writePanelLayout({ ...readPanelLayout(), [side]: value });
  }, []);

  const onLeftResize = useCallback(
    (size: number) => {
      if (dragging.current) persist('left', (size / 100) * width);
    },
    [persist, width],
  );
  const onRightResize = useCallback(
    (size: number) => {
      if (dragging.current) persist('right', (size / 100) * width);
    },
    [persist, width],
  );
  const onDragging = useCallback((isDragging: boolean) => {
    dragging.current = isDragging;
  }, []);

  return {
    groupRef,
    leftRef,
    rightRef,
    onDragging,
    left: {
      defaultSize: pct(widths.left),
      minSize: pct(LEFT_MIN_PX),
      maxSize: pct(LEFT_MAX_PX),
      onResize: onLeftResize,
    },
    right: {
      defaultSize: pct(widths.right),
      minSize: pct(RIGHT_MIN_PX),
      maxSize: pct(RIGHT_MAX_PX),
      onResize: onRightResize,
    },
  };
}

/**
 * Whether the viewport is at least `px` wide (false until mounted). Reads `innerWidth` on each
 * media-query change, the way `useIsMobile` does, so it also answers where `matchMedia` is a stub.
 */
export function useMinWidth(px: number): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const update = () => setWide(window.innerWidth >= px);
    update();
    const mql = window.matchMedia?.(`(min-width: ${px}px)`);
    mql?.addEventListener?.('change', update);
    window.addEventListener('resize', update);
    return () => {
      mql?.removeEventListener?.('change', update);
      window.removeEventListener('resize', update);
    };
  }, [px]);
  return wide;
}
