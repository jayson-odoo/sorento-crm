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
 * Health-state presentation registry. Colour is NEVER the sole signal - every
 * state pairs its diverging-ramp token (defined in css/config.reui.css as
 * `--scm-*`, theme-aware light+dark) with an icon + a human label.
 *
 * `deferred: true` states are rendered disabled/muted - they light up when the
 * backing data exists. `overstock` is ACTIVE (days-of-cover over the ceiling,
 * computed + filtered server-side). `low` (below reorder point) is ACTIVE as of
 * M8-B: the demand-aware engine reorder point (latest completed run) is real, so
 * a stocked SKU with `net <= reorder_point` reads as "Low stock".
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
    label: 'Out of stock',
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
    label: 'Low stock',
    icon: TrendingDown,
    solidClass: 'bg-scm-low',
    softClass: 'bg-scm-low-soft',
    textClass: 'text-scm-low',
    barClass: 'bg-scm-low',
    // ACTIVE as of M8-B: the demand-aware engine reorder point (latest completed
    // run) is real, so a stocked SKU with net <= reorder_point reads as Low stock.
    deferred: false,
    intent: 'In stock but at or below the reorder point',
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
    // Active - demand-derived (days-of-cover over the ceiling), computed +
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

/** States wired with real data, worst-first (drives legend + composition order).
 *  `low` (below reorder point) joined the active set at M8-B. */
export const M1_ACTIVE_STATES: HealthState[] = [
  'stockout',
  'dead',
  'low',
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
 * and the Phase-2 backend contract stay industry-standard ABC/XYZ - this is a
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
