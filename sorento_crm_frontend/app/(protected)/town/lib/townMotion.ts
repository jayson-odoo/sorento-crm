import type { TownSnapshot } from '@/types/town.types';

/**
 * The town's motion vocabulary (approved v6 mock): one curve, the repo's `--ease-standard`
 * (`cubic-bezier(0.2, 0, 0, 1)`, css/config.reui.css), solved exactly; anything with mass (lorries,
 * ships, the crane) moves on a trapezoid speed profile; springs are analytic damped sines. No other curves.
 */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number): (x: number) => number {
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  const dsx = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const e = sx(t) - x;
      if (Math.abs(e) < 1e-6) return sy(t);
      const d = dsx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    let lo = 0;
    let hi = 1;
    t = x;
    for (let i = 0; i < 40; i++) {
      const v = sx(t);
      if (Math.abs(v - x) < 1e-6) break;
      if (x > v) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sy(t);
  };
}

/** `--ease-standard`. */
export const EASE = cubicBezier(0.2, 0, 0, 1);

export interface Trapezoid {
  /** Total time and distance. */
  T: number;
  L: number;
  at: (t: number) => number;
  vel: (t: number) => number;
  acc: (t: number) => number;
}

/** Distance, speed and acceleration over time for a body that covers `L` at top speed `v` and
 * acceleration `a`, starting and stopping at rest. */
export function trapezoid(L: number, v: number, a: number): Trapezoid {
  const ta = v / a;
  const da = 0.5 * a * ta * ta;
  if (2 * da >= L) {
    const t1 = Math.sqrt(L / a);
    const T = 2 * t1;
    return {
      T,
      L,
      at: (t) => (t <= 0 ? 0 : t >= T ? L : t < t1 ? 0.5 * a * t * t : L - 0.5 * a * (T - t) ** 2),
      vel: (t) => (t <= 0 || t >= T ? 0 : t < t1 ? a * t : a * (T - t)),
      acc: (t) => (t <= 0 || t >= T ? 0 : t < t1 ? a : -a),
    };
  }
  const tc = (L - 2 * da) / v;
  const T = 2 * ta + tc;
  return {
    T,
    L,
    at: (t) =>
      t <= 0 ? 0 : t >= T ? L : t < ta ? 0.5 * a * t * t : t < ta + tc ? da + v * (t - ta) : L - 0.5 * a * (T - t) ** 2,
    vel: (t) => (t <= 0 || t >= T ? 0 : t < ta ? a * t : t < ta + tc ? v : a * (T - t)),
    acc: (t) => (t <= 0 || t >= T ? 0 : t < ta ? a : t < ta + tc ? 0 : -a),
  };
}

/** A small seeded random source, so the trees and the sparkles fall the same way on every load. */
export function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** One shop that invoiced again since the last poll: how many more invoices, and how much more
 * (null when the viewer may not see amounts). */
export interface SaleShop {
  key: string;
  docs: number;
  amount: number | null;
}

/** What one poll brought: the shops with new invoices (busiest first), the new invoices in all, and
 * their summed amount (null when any amount is hidden from this viewer). */
export interface SaleBeat {
  shops: SaleShop[];
  invoices: number;
  amount: number | null;
}

/**
 * The new sales between two snapshots, for the one beat a poll plays (TOWN-V2 rule 10). Nothing on
 * the first load, across a day or company change, or when no shop has more `today_docs` than before.
 */
export function newSales(prev: TownSnapshot | null | undefined, next: TownSnapshot): SaleBeat | null {
  if (!prev || prev === next || prev.day !== next.day || prev.company_id !== next.company_id) return null;
  const before = new Map(prev.shops.map((shop) => [shop.key, shop]));
  const shops: SaleShop[] = [];
  for (const shop of next.shops) {
    const old = before.get(shop.key);
    const docs = shop.today_docs - (old?.today_docs ?? 0);
    if (docs <= 0) continue;
    const amount =
      shop.today_amount != null && (old?.today_amount != null || !old?.today_docs)
        ? Number(shop.today_amount) - Number(old?.today_amount ?? 0)
        : null;
    shops.push({ key: shop.key, docs, amount });
  }
  if (!shops.length) return null;
  shops.sort((a, b) => b.docs - a.docs || (b.amount ?? 0) - (a.amount ?? 0));
  const shown = next.today.amount != null && shops.every((shop) => shop.amount !== null);
  return {
    shops,
    invoices: shops.reduce((sum, shop) => sum + shop.docs, 0),
    amount: shown ? shops.reduce((sum, shop) => sum + (shop.amount as number), 0) : null,
  };
}
