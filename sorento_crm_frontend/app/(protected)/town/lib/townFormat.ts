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
export const SCENE_TAG_CAP = 5;

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

const HALF_HEIGHT = 30; // the island's ellipse plus the scoreboard above it, in world units
const HALF_WIDTH = 36; // the island's radius plus the half width of an outer tag
const HALF_WIDTH_SMALL = 42; // tags are drawn larger on a phone

/** Half the visible height, in world units, that fits the whole island in a canvas of this shape. */
export function townFrame(aspect: number, small: boolean): number {
  return Math.max(HALF_HEIGHT, (small ? HALF_WIDTH_SMALL : HALF_WIDTH) / aspect);
}
