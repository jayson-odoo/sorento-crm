'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

const FALLBACK_COLOR = '#64748b';

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '').match(/^([0-9a-fA-F]{6})$/);
  if (!m) return `rgba(100, 116, 139, ${alpha})`;
  const r = parseInt(m[1].slice(0, 2), 16);
  const g = parseInt(m[1].slice(2, 4), 16);
  const b = parseInt(m[1].slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export type StatusPillProps = {
  label: string;
  colorHex?: string | null;
  className?: string;
};

export function StatusPill({ label, colorHex, className }: StatusPillProps) {
  const color = (colorHex || '').trim() || FALLBACK_COLOR;
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-xs font-medium border',
        className,
      )}
      style={{
        backgroundColor: hexToRgba(color, 0.12),
        borderColor: hexToRgba(color, 0.4),
        color,
      }}
    >
      {label}
    </span>
  );
}
