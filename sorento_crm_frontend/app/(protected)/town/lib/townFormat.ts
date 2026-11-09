import type { TownShop, TownSnapshot } from '@/types/town.types';

export const rm = (value: string) =>
  `RM ${Number(value).toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const rm0 = (value: string) => `RM ${Math.round(Number(value)).toLocaleString('en-MY')}`;
export const count = (value: number) => value.toLocaleString('en-MY');

/** "ZZT Tiling One SDN BHD [A/C III]" reads "ZZT Tiling One [A/C III]" on a card. */
export const shortName = (name: string) =>
  name
    .replace(/\s*(SDN\.?\s*BHD\.?|ENTERPRISE|MARKETING|TRADING|\(M\))/gi, '')
    .replace(/\s+/g, ' ')
    .trim();

/** What a shop is called to this viewer: a name, a rank on the wallboard, "Dealer" when anonymous. */
export function shopLabel(shop: TownShop): string {
  if (shop.name) return shortName(shop.name);
  return shop.rank ? `Shop #${shop.rank}` : 'Dealer';
}

/** "RM 9,589" when the viewer may see amounts, else "3 inv". */
export function shopToday(shop: TownShop): string {
  return shop.today_amount ? rm0(shop.today_amount) : `${shop.today_docs} inv`;
}

/** Change against the same weekday last week, in percent; null when either figure is hidden. */
export function changePercent(snapshot: TownSnapshot): number | null {
  const now = snapshot.today.amount;
  const before = snapshot.compare?.last_week_amount;
  if (now == null || before == null || Number(before) === 0) return null;
  return ((Number(now) - Number(before)) / Number(before)) * 100;
}

export const signedPercent = (pct: number) => `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%`;

const byToday = (a: TownShop, b: TownShop) =>
  b.today_docs - a.today_docs || Number(b.today_amount ?? 0) - Number(a.today_amount ?? 0);

/** The shops that bought today, busiest first, and the dealers beyond them with no building. */
export function boughtToday(snapshot: TownSnapshot) {
  const bought = snapshot.shops.filter((shop) => shop.today_docs > 0).sort(byToday);
  const others = Math.max(0, snapshot.today.dealer_customer_count - bought.length);
  return { bought, others };
}

export const SCENE_STALL_CAP = 5;
export const SCENE_TAG_CAP = 3; // one tier each, so no two tags can ever cover each other

/**
 * What the 3D town draws, so a day with sixty stalls stays readable: every top shop, at most five
 * stalls (busiest first), a name tag on at most five lit buildings (busiest first), and "+N more
 * dealers" for the invoiced dealers that have no building drawn.
 */
export function sceneSelection(snapshot: TownSnapshot) {
  const shops = snapshot.shops.filter((shop) => shop.kind === 'shop');
  const stalls = snapshot.shops
    .filter((shop) => shop.kind !== 'shop')
    .sort(byToday)
    .slice(0, SCENE_STALL_CAP);
  const drawn = [...shops, ...stalls];
  const lit = drawn.filter((shop) => shop.today_docs > 0);
  const tagged = [...lit].sort(byToday).slice(0, SCENE_TAG_CAP);
  return { drawn, tagged, others: Math.max(0, snapshot.today.dealer_customer_count - lit.length) };
}

// The camera is orthographic at a fixed elevation (atan(70/80), 41 degrees), so the island's
// projected size is known: its ground disc is 56 wide (R = 28) and 37 high on screen, the scoreboard
// and the labels add to the height, and the outer name tags reach past the disc's edge. The view is
// sized so that content fills 95% of the tighter dimension (the approved mock fills about 95%).
const HALF_HEIGHT = 21;
const HALF_WIDTH = 30; // the island's radius plus the part of an outer tag that sticks out
const HALF_WIDTH_SMALL = 33.5; // tags are drawn larger on a phone
const FILL = 0.95;

/** Half the visible height, in world units, that fits the island and its labels in a canvas of this shape. */
export function townFrame(aspect: number, small: boolean): number {
  return Math.max(HALF_HEIGHT, (small ? HALF_WIDTH_SMALL : HALF_WIDTH) / aspect) / FILL;
}

const TAG_NAME_MAX = 22;

/** A tag's text: the short name capped at 22 characters with an ellipsis, always followed by the amount. */
export function tagLabel(shop: TownShop): string {
  const name = shopLabel(shop);
  const capped = name.length > TAG_NAME_MAX ? `${name.slice(0, TAG_NAME_MAX - 1).trimEnd()}\u2026` : name;
  return shop.today_amount ? `${capped}  ${rm0(shop.today_amount)}` : capped;
}

/** A count for the small icon tile: exact up to 999, then "2.2k" (the big number on the card stays exact). */
export function compactCount(value: number): string {
  if (value < 1000) return String(value);
  const thousands = (value / 1000).toFixed(1).replace(/\.0$/, '');
  return `${thousands}k`;
}

export interface TagBox {
  /** The anchor's height on screen, and its centre across the screen (optional: without it, every
   * box counts as in the way of every other). */
  y: number;
  h: number;
  x?: number;
  w?: number;
}

const apart = (a: TagBox, b: TagBox) =>
  a.x !== undefined && a.w !== undefined && b.x !== undefined && b.w !== undefined
    ? Math.abs(a.x - b.x) >= (a.w + b.w) / 2
    : false;

/**
 * Screen-space stacking for the name tags. Tags are taken bottom to top and each one is raised just
 * enough to clear every box already placed that it overlaps across the screen: the tags below it and
 * the fixed `obstacles` (the scoreboard, the "+N more dealers" pill), which never move. No two tags
 * cover each other or an obstacle whatever the camera angle or the buildings' depth.
 *
 * `top` is the highest a tag may reach on screen. When a tag would pass it, the lowest priority tag
 * (the last in the input) is dropped and the rest are stacked again, rather than clip one at the edge.
 * Returns how far to raise each tag, on screen, in input order; null for a dropped tag.
 */
export function stackTags(
  tags: TagBox[],
  margin = 0.3,
  options: { obstacles?: TagBox[]; top?: number } = {},
): (number | null)[] {
  const { obstacles = [], top = Infinity } = options;
  const layout = (active: number[]) => {
    const placed = obstacles.map((box) => ({ box, bottom: box.y - box.h / 2 }));
    const raise = new Map<number, number>();
    let highest = -Infinity;
    for (const index of [...active].sort((a, b) => tags[a].y - tags[b].y)) {
      const tag = tags[index];
      let bottom = tag.y - tag.h / 2;
      for (let moved = true; moved; ) {
        moved = false;
        for (const other of placed) {
          if (apart(tag, other.box)) continue;
          const otherTop = other.bottom + other.box.h;
          if (bottom < otherTop + margin && bottom + tag.h > other.bottom - margin) {
            bottom = otherTop + margin;
            moved = true;
          }
        }
      }
      placed.push({ box: tag, bottom });
      raise.set(index, bottom + tag.h / 2 - tag.y);
      highest = Math.max(highest, bottom + tag.h);
    }
    return { raise, highest };
  };
  const active = tags.map((_, index) => index);
  let result = layout(active);
  while (result.highest > top && active.length > 0) {
    active.pop();
    result = layout(active);
  }
  return tags.map((_, index) => result.raise.get(index) ?? null);
}

/** A box on screen: its centre `x`, `y` and its size. */
export interface ScreenBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Moves `box` the least that puts it wholly inside `view` (the canvas edges in the same screen units),
 * so a label turned toward the edge is never cut off. Returns the box's centre; a box bigger than the
 * view is centred.
 */
export function clampInView(
  box: ScreenBox,
  view: { left: number; right: number; bottom: number; top: number },
  margin = 0.3,
): { x: number; y: number } {
  const clamp = (value: number, low: number, high: number) => (low > high ? (low + high) / 2 : Math.min(Math.max(value, low), high));
  return {
    x: clamp(box.x, view.left + box.w / 2 + margin, view.right - box.w / 2 - margin),
    y: clamp(box.y, view.bottom + box.h / 2 + margin, view.top - box.h / 2 - margin),
  };
}
