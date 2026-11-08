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
// projected size is known: its width is 2R (R = 28), its height 2R * sin(elevation) = 37 plus the
// scoreboard and the label tiers above it. Half of that, with the outer labels, and 90% fill.
const HALF_HEIGHT = 21;
const HALF_WIDTH = 31; // the island's radius plus the half width of an outer tag
const HALF_WIDTH_SMALL = 35; // tags are drawn larger on a phone
const FILL = 0.9;

/** Half the visible height, in world units, that fits the island and its labels in a canvas of this shape. */
export function townFrame(aspect: number, small: boolean): number {
  return Math.max(HALF_HEIGHT, (small ? HALF_WIDTH_SMALL : HALF_WIDTH) / aspect) / FILL;
}

/**
 * Screen-space stacking for the name tags. Each tag has `y`, its anchor's height on screen (the
 * anchor projected on the camera's up axis), and `h`, its height on screen. Tags are taken bottom to
 * top and each one is raised just enough to clear the one below it, so no two tags ever cover each
 * other whatever the camera angle or the buildings' depth (tags at different depths are why fixed
 * world-height tiers still overlapped). Returns how far to raise each tag, on screen, in input order.
 */
export function stackTags(tags: { y: number; h: number }[], margin = 0.3): number[] {
  const order = tags.map((tag, index) => ({ ...tag, index })).sort((a, b) => a.y - b.y);
  const raise = new Array<number>(tags.length).fill(0);
  let top = -Infinity;
  for (const tag of order) {
    const bottom = Math.max(tag.y - tag.h / 2, top + margin);
    raise[tag.index] = bottom + tag.h / 2 - tag.y;
    top = bottom + tag.h;
  }
  return raise;
}

