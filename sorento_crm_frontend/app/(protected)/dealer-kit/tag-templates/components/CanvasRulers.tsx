'use client';

/**
 * MM rulers rendered along the top and left edges of the canvas workspace.
 *
 * Tick marks every 5 mm, numbers every 10 mm. Uses plain DOM/CSS, not Konva,
 * so rulers stay outside the canvas bitmap.
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
  /** Horizontal scroll offset in px (for future scroll support). */
  scrollX?: number;
  /** Vertical scroll offset in px. */
  scrollY?: number;
}

export function CanvasRulers({
  widthMm,
  heightMm,
  scale,
  scrollX = 0,
  scrollY = 0,
}: CanvasRulersProps) {
  const hTicks = useMemo(() => {
    const ticks: { pos: number; mm: number; major: boolean }[] = [];
    for (let mm = 0; mm <= widthMm; mm += 5) {
      ticks.push({ pos: mm * scale + scrollX, mm, major: mm % 10 === 0 });
    }
    return ticks;
  }, [widthMm, scale, scrollX]);

  const vTicks = useMemo(() => {
    const ticks: { pos: number; mm: number; major: boolean }[] = [];
    for (let mm = 0; mm <= heightMm; mm += 5) {
      ticks.push({ pos: mm * scale + scrollY, mm, major: mm % 10 === 0 });
    }
    return ticks;
  }, [heightMm, scale, scrollY]);

  return (
    <>
      {/* Top ruler */}
      <div
        className="absolute top-0 bg-muted border-b border-border overflow-hidden"
        style={{
          left: RULER_THICKNESS,
          height: RULER_THICKNESS,
          width: widthMm * scale,
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
                className="absolute bottom-[10px] text-[8px] leading-none text-muted-foreground select-none"
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
        className="absolute left-0 bg-muted border-r border-border overflow-hidden"
        style={{
          top: RULER_THICKNESS,
          width: RULER_THICKNESS,
          height: heightMm * scale,
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
                className="absolute right-[10px] text-[8px] leading-none text-muted-foreground select-none"
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
        className="absolute top-0 left-0 bg-muted border-b border-r border-border"
        style={{ width: RULER_THICKNESS, height: RULER_THICKNESS }}
      />
    </>
  );
}

export { RULER_THICKNESS };
