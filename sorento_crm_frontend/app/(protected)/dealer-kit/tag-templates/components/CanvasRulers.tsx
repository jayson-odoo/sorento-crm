'use client';

/**
 * MM rulers along the top and left edges of the canvas workspace.
 *
 * Viewport-wide strips, not artboard-wide ones (D33): the Stage now fills the
 * workspace and the artboard sits at a pan offset inside it, so a tick belongs
 * at `origin + mm * scale` and the strip has to be as long as the viewport or
 * it stops before the artboard does at any pan.
 *
 * Tick marks every 5 mm, numbers every 10 mm. Plain DOM and CSS, not Konva, so
 * the rulers stay outside the canvas bitmap.
 *
 * Both rulers also spawn guides (D9/D17, S6): a `mousedown` here starts the
 * gesture and reports the ORIENTATION plus the raw event - the host (which
 * already owns pan/zoom/the container) turns that into an mm position and
 * owns the guide's whole lifecycle from there, the same way it already owns
 * marquee and pan. A ruler div's own left/top edge sits at the same pixel as
 * the Stage's own x/y = 0 (both are positioned at `RULER_THICKNESS` from the
 * same container), so no extra plumbing is needed to line the two up.
 *
 * One guide per axis (D21, S8): each ruler also carries a small x chip at its
 * own guide's position, one more removal path besides drag-back-to-the-ruler
 * and Delete/Backspace. The chip sits OUTSIDE the ruler strip's own
 * `overflow-hidden` div (a sibling, not a child) so it is never clipped by it.
 */

import { useMemo } from 'react';
import { X } from 'lucide-react';

/** Width (left ruler) / height (top ruler) of the ruler strip in px. */
const RULER_THICKNESS = 20;

interface CanvasRulersProps {
  /** Tag width in mm. */
  widthMm: number;
  /** Tag height in mm. */
  heightMm: number;
  /** Pixels per mm at the current zoom. */
  scale: number;
  /** The artboard origin in stage px: where 0 mm falls along each strip. */
  originX: number;
  originY: number;
  /** Size of the Stage the strips run alongside, in px. */
  viewportWidth: number;
  viewportHeight: number;
  /**
   * A guide-drop gesture started on this ruler (D9/D17). `orientation` names
   * which kind of guide it spawns - `'vertical'` for the top ruler,
   * `'horizontal'` for the left one - not which ruler was clicked.
   */
  onGuideStart?: (orientation: 'vertical' | 'horizontal', event: React.MouseEvent) => void;
  /** Where the axis's one guide sits, in mm - `null` when that axis has none (D21). */
  verticalGuideMm?: number | null;
  horizontalGuideMm?: number | null;
  /** The chip at a guide's own ruler position was clicked (D21, AC-S8-2). */
  onGuideRemove?: (orientation: 'vertical' | 'horizontal') => void;
}

export function CanvasRulers({
  widthMm,
  heightMm,
  scale,
  originX,
  originY,
  viewportWidth,
  viewportHeight,
  onGuideStart,
  verticalGuideMm,
  horizontalGuideMm,
  onGuideRemove,
}: CanvasRulersProps) {
  const hTicks = useMemo(() => {
    const ticks: { pos: number; mm: number; major: boolean }[] = [];
    for (let mm = 0; mm <= widthMm; mm += 5) {
      const pos = originX + mm * scale;
      if (pos < -20 || pos > viewportWidth + 20) continue;
      ticks.push({ pos, mm, major: mm % 10 === 0 });
    }
    return ticks;
  }, [widthMm, scale, originX, viewportWidth]);

  const vTicks = useMemo(() => {
    const ticks: { pos: number; mm: number; major: boolean }[] = [];
    for (let mm = 0; mm <= heightMm; mm += 5) {
      const pos = originY + mm * scale;
      if (pos < -20 || pos > viewportHeight + 20) continue;
      ticks.push({ pos, mm, major: mm % 10 === 0 });
    }
    return ticks;
  }, [heightMm, scale, originY, viewportHeight]);

  // Where the guide chips land, in the same stage-px space as the ticks
  // above - `null` when that axis has no guide. Unlike the ticks (which cull
  // off-screen ones for a long ruler's sake), there is only ever ONE chip per
  // axis, so it is left to the workspace container's own `overflow-hidden`
  // to clip it when it has panned out of view rather than duplicating that
  // bound here.
  const verticalChipPos = useMemo(
    () => (verticalGuideMm == null ? null : originX + verticalGuideMm * scale),
    [verticalGuideMm, originX, scale],
  );

  const horizontalChipPos = useMemo(
    () => (horizontalGuideMm == null ? null : originY + horizontalGuideMm * scale),
    [horizontalGuideMm, originY, scale],
  );

  return (
    <>
      {/* Top ruler - drops a VERTICAL guide (it measures X, D17). */}
      <div
        className="absolute top-0 cursor-col-resize overflow-hidden border-b border-border bg-muted"
        style={{
          left: RULER_THICKNESS,
          height: RULER_THICKNESS,
          width: viewportWidth,
        }}
        onMouseDown={(event) => onGuideStart?.('vertical', event)}
      >
        {hTicks.map((t) => (
          <div
            key={`h-${t.mm}`}
            className="absolute top-0"
            style={{ left: t.pos, height: '100%' }}
          >
            <div
              className="absolute bottom-0 w-px bg-muted-foreground/50"
              style={{ height: t.major ? 10 : 5 }}
            />
            {t.major && (
              <span
                className="absolute bottom-[10px] select-none text-[8px] leading-none text-muted-foreground"
                style={{ transform: 'translateX(-50%)' }}
              >
                {t.mm}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Left ruler - drops a HORIZONTAL guide (it measures Y, D17). */}
      <div
        className="absolute left-0 cursor-row-resize overflow-hidden border-r border-border bg-muted"
        style={{
          top: RULER_THICKNESS,
          width: RULER_THICKNESS,
          height: viewportHeight,
        }}
        onMouseDown={(event) => onGuideStart?.('horizontal', event)}
      >
        {vTicks.map((t) => (
          <div
            key={`v-${t.mm}`}
            className="absolute left-0"
            style={{ top: t.pos, width: '100%' }}
          >
            <div
              className="absolute right-0 h-px bg-muted-foreground/50"
              style={{ width: t.major ? 10 : 5 }}
            />
            {t.major && (
              <span
                className="absolute right-[10px] select-none text-[8px] leading-none text-muted-foreground"
                style={{ transform: 'translateY(-50%)' }}
              >
                {t.mm}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Corner square */}
      <div
        className="absolute left-0 top-0 border-b border-r border-border bg-muted"
        style={{ width: RULER_THICKNESS, height: RULER_THICKNESS }}
      />

      {/* Guide chips (D21, AC-S8-2): sit OUTSIDE the ruler strips above (not
          nested inside their own `overflow-hidden`), positioned at the guide's
          own coordinate along the ruler it came from. */}
      {verticalChipPos != null && (
        <button
          type="button"
          className="absolute z-10 flex size-3.5 items-center justify-center rounded-full border border-sky-500 bg-background text-sky-600 shadow-sm hover:bg-sky-50"
          style={{
            left: RULER_THICKNESS + verticalChipPos - 7,
            top: RULER_THICKNESS / 2 - 7,
          }}
          title="Remove guide"
          aria-label="Remove vertical guide"
          onClick={() => onGuideRemove?.('vertical')}
        >
          <X className="size-2.5" />
        </button>
      )}
      {horizontalChipPos != null && (
        <button
          type="button"
          className="absolute z-10 flex size-3.5 items-center justify-center rounded-full border border-sky-500 bg-background text-sky-600 shadow-sm hover:bg-sky-50"
          style={{
            left: RULER_THICKNESS / 2 - 7,
            top: RULER_THICKNESS + horizontalChipPos - 7,
          }}
          title="Remove guide"
          aria-label="Remove horizontal guide"
          onClick={() => onGuideRemove?.('horizontal')}
        >
          <X className="size-2.5" />
        </button>
      )}
    </>
  );
}

export { RULER_THICKNESS };
