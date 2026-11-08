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

/** The shops that bought today, and the dealers beyond them that the scene has no building for. */
export function boughtToday(snapshot: TownSnapshot) {
  const bought = snapshot.shops.filter((shop) => shop.today_docs > 0);
  const others = Math.max(0, snapshot.today.dealer_customer_count - bought.length);
  return { bought, others };
}
