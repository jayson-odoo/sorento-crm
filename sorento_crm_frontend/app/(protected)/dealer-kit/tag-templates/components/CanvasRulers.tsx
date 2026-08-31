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
 */

import { useMemo } from 'react';

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
}

export function CanvasRulers({
  widthMm,
  heightMm,
  scale,
  originX,
  originY,
  viewportWidth,
  viewportHeight,
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

  return (
    <>
      {/* Top ruler */}
      <div
        className="absolute top-0 overflow-hidden border-b border-border bg-muted"
        style={{
          left: RULER_THICKNESS,
          height: RULER_THICKNESS,
          width: viewportWidth,
        }}
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

      {/* Left ruler */}
      <div
        className="absolute left-0 overflow-hidden border-r border-border bg-muted"
        style={{
          top: RULER_THICKNESS,
          width: RULER_THICKNESS,
          height: viewportHeight,
        }}
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
    </>
  );
}

export { RULER_THICKNESS };
