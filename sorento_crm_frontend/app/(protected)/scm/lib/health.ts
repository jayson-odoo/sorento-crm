import {
  AlertTriangle,
  Ban,
  CircleCheck,
  Layers,
  TrendingDown,
  Truck,
  type LucideIcon,
} from 'lucide-react';
import type { AbcClass, HealthState, XyzClass } from '../types/scm.types';

/**
 * Health-state presentation registry. Colour is NEVER the sole signal — every
 * state pairs its diverging-ramp token (defined in css/config.reui.css as
 * `--scm-*`, theme-aware light+dark) with an icon + a human label.
 *
 * `deferred: true` states are rendered disabled/muted — they light up when the
 * backing data exists. `overstock` is ACTIVE (days-of-cover over the ceiling,
 * computed + filtered server-side). `low` (below reorder point) stays DEFERRED
 * to M3: a real reorder point needs demand × lead time + safety stock, which
 * doesn't exist until M3 — we never fake it. The reorder-point *column* is
 * likewise deferred (M3).
 */
export interface HealthStateMeta {
  state: HealthState;
  label: string;
  icon: LucideIcon;
  /** Accent bar / icon / emphasis ink. */
  solidClass: string;
  /** Badge/tile tint background. */
  softClass: string;
  /** Ink used on top of the soft tint. */
  textClass: string;
  /** Mini-bar segment fill. */
  barClass: string;
  /** Prototyped but not wired with real data at M1. */
  deferred: boolean;
  /** One-line intent, used in the legend + tile titles. */
  intent: string;
}

export const HEALTH_STATES: Record<HealthState, HealthStateMeta> = {
  stockout: {
    state: 'stockout',
    label: 'Stockout',
    icon: AlertTriangle,
    solidClass: 'bg-scm-stockout',
    softClass: 'bg-scm-stockout-soft',
    textClass: 'text-scm-stockout',
    barClass: 'bg-scm-stockout',
    deferred: false,
    intent: 'On-hand is zero',
  },
  low: {
    state: 'low',
    label: 'Low / reorder-due',
    icon: TrendingDown,
    solidClass: 'bg-scm-low',
    softClass: 'bg-scm-low-soft',
    textClass: 'text-scm-low',
    barClass: 'bg-scm-low',
    // DEFERRED to M3. A real reorder point = demand × lead time + safety stock,
    // none of which exists until M3, so this legend chip stays inactive/greyed
    // ("later step") — we never fabricate a reorder point. Do NOT flip to false
    // until the M3 reorder-point engine lands.
    deferred: true,
    intent: 'Below reorder point',
  },
  healthy: {
    state: 'healthy',
    label: 'Healthy',
    icon: CircleCheck,
    solidClass: 'bg-scm-healthy',
    softClass: 'bg-scm-healthy-soft',
    textClass: 'text-scm-healthy',
    barClass: 'bg-scm-healthy',
    deferred: false,
    intent: 'Positive net position',
  },
  overstock: {
    state: 'overstock',
    label: 'Overstock',
    icon: Layers,
    solidClass: 'bg-scm-overstock',
    softClass: 'bg-scm-overstock-soft',
    textClass: 'text-scm-overstock',
    barClass: 'bg-scm-overstock',
    // Active — demand-derived (days-of-cover over the ceiling), computed +
    // filtered server-side.
    deferred: false,
    intent: 'Days-of-cover over ceiling',
  },
  dead: {
    state: 'dead',
    label: 'Dead',
    icon: Ban,
    solidClass: 'bg-scm-dead',
    softClass: 'bg-scm-dead-soft',
    textClass: 'text-scm-dead',
    barClass: 'bg-scm-dead',
    deferred: false,
    intent: 'No movement beyond dead-stock window',
  },
  incoming: {
    state: 'incoming',
    label: 'Incoming PO',
    icon: Truck,
    solidClass: 'bg-scm-incoming',
    softClass: 'bg-scm-incoming-soft',
    textClass: 'text-scm-incoming',
    barClass: 'bg-scm-incoming',
    deferred: false,
    intent: 'Open purchase order inbound',
  },
};

/** States wired with real data at M1, worst-first (drives legend + composition order). */
export const M1_ACTIVE_STATES: HealthState[] = [
  'stockout',
  'dead',
  'healthy',
  'incoming',
];

export function healthMeta(state: HealthState): HealthStateMeta {
  return HEALTH_STATES[state];
}

/**
 * Plain-language DISPLAY labels for the ABC / XYZ analytics classes.
 *
 * The underlying values (`abc_class` = 'A'|'B'|'C', `xyz_class` = 'X'|'Y'|'Z')
 * and the Phase-2 backend contract stay industry-standard ABC/XYZ — this is a
 * UI relabel ONLY so the jargon never reaches the screen:
 *   ABC → "Value"  : A → High, B → Med, C → Low, null → Unknown.
 *   XYZ → "Demand" : X → Steady, Y → Variable, Z → Erratic, null → Unknown.
 * Consumed by ClassChip, the Product grid + drill-down popup columns, and the
 * filter bar. Keep the maps as the single source of truth for the wording.
 */
export const ABC_HEADER = 'Value';
export const XYZ_HEADER = 'Demand';
export const UNKNOWN_CLASS_LABEL = 'Unknown';

export const ABC_DISPLAY: Record<AbcClass, string> = { A: 'High', B: 'Med', C: 'Low' };
export const XYZ_DISPLAY: Record<XyzClass, string> = {
  X: 'Steady',
  Y: 'Variable',
  Z: 'Erratic',
};

export function abcLabel(value: AbcClass | null | undefined): string {
  return value ? ABC_DISPLAY[value] : UNKNOWN_CLASS_LABEL;
}

export function xyzLabel(value: XyzClass | null | undefined): string {
  return value ? XYZ_DISPLAY[value] : UNKNOWN_CLASS_LABEL;
}
