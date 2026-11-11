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
export const SCENE_TAG_CAP = 3; // a calm town: the three busiest lit buildings carry a name tag

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

const TAG_NAME_MAX = 22;

/** A tag's name: the short name capped at 22 characters with an ellipsis. */
export function tagName(shop: TownShop): string {
  const name = shopLabel(shop);
  return name.length > TAG_NAME_MAX ? `${name.slice(0, TAG_NAME_MAX - 1).trimEnd()}\u2026` : name;
}

/** A tag's text: the capped name, always followed by the amount when the viewer may see it. */
export function tagLabel(shop: TownShop): string {
  const capped = tagName(shop);
  return shop.today_amount ? `${capped}  ${rm0(shop.today_amount)}` : capped;
}

/** A count for the small icon tile: exact up to 999, then "2.2k" (the big number on the card stays exact). */
export function compactCount(value: number): string {
  if (value < 1000) return String(value);
  const thousands = (value / 1000).toFixed(1).replace(/\.0$/, '');
  return `${thousands}k`;
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

const overlapsBox = (a: ScreenBox, b: ScreenBox, margin: number) =>
  Math.abs(a.x - b.x) < (a.w + b.w) / 2 + margin && Math.abs(a.y - b.y) < (a.h + b.h) / 2 + margin;

/**
 * Where the fixed labels (the "!" bubble, the depot sign, the approvals badge, the "+N" pill) sit on
 * screen so that none covers the scoreboard or another one, whatever angle the town is turned to.
 * Each label is first clamped inside the view, then moved only up or down the screen to the nearest
 * spot (above or below any box already placed) that is clear of every placed box and inside the view.
 * Labels are placed lowest first, the scoreboard first of all. A fixed label is never dropped: if no
 * clear spot is inside the view it stays at its clamped position. Returns the centres, in input order.
 */
export function separateLabels(
  labels: ScreenBox[],
  board: ScreenBox,
  view: { left: number; right: number; bottom: number; top: number },
  margin = 0.3,
): { x: number; y: number }[] {
  const placed: ScreenBox[] = [board];
  const out = new Array<{ x: number; y: number }>(labels.length);
  const order = labels.map((_, index) => index).sort((a, b) => labels[a].y - labels[b].y);
  const eps = 1e-6;
  for (const index of order) {
    const label = labels[index];
    const base = clampInView(label, view, margin);
    const at = (y: number): ScreenBox => ({ ...label, x: base.x, y });
    const candidates = [base.y];
    for (const other of placed) {
      candidates.push(other.y + other.h / 2 + margin + label.h / 2 + eps);
      candidates.push(other.y - other.h / 2 - margin - label.h / 2 - eps);
    }
    const clear = candidates
      .filter((y) => y - label.h / 2 >= view.bottom + margin - eps && y + label.h / 2 <= view.top - margin + eps)
      .filter((y) => placed.every((other) => !overlapsBox(at(y), other, margin - eps)))
      .sort((a, b) => Math.abs(a - base.y) - Math.abs(b - base.y));
    const y = clear.length ? clear[0] : base.y;
    placed.push(at(y));
    out[index] = { x: base.x, y };
  }
  return out;
}

/**
 * Where the shop tags sit on screen (the v6 DOM pills), after the fixed labels have been placed. Each
 * tag, in priority order, tries its anchor, then a step up, a step down, a step to each side and so on,
 * and takes the first spot clear of every box already placed; a tag with no clear spot is culled
 * (null) rather than drawn over another label. With a `view`, every spot is first pulled inside it,
 * so a tag is never clipped by the stage edge. `null` in `tags` is a tag off screen. Returns the
 * centres in input order.
 */
export function placeTags(
  tags: (ScreenBox | null)[],
  placed: ScreenBox[],
  view?: { left: number; right: number; bottom: number; top: number },
  margin = 3,
): ({ x: number; y: number } | null)[] {
  const taken = [...placed];
  return tags.map((tag) => {
    if (!tag) return null;
    const step = tag.h + 4;
    const side = tag.w / 2 + 6;
    const tries = [[0, 0], [0, -step], [0, step], [side, 0], [-side, 0], [0, -2 * step], [side, -step], [-side, -step]];
    for (const [ox, oy] of tries) {
      const moved: ScreenBox = { ...tag, x: tag.x + ox, y: tag.y + oy };
      const at: ScreenBox = view ? { ...moved, ...clampInView(moved, view, margin) } : moved;
      if (taken.every((other) => !overlapsBox(at, other, margin))) {
        taken.push(at);
        return { x: at.x, y: at.y };
      }
    }
    return null;
  });
}

/** TOWN-PROJECT-CITY: "Dealers RM 300 · Projects RM 150 · Other RM 30" (adds up to the day's figure), or the invoice
 * counts for a viewer without amounts; null on a snapshot built before the split existed. */
export function splitLine(today: TownSnapshot['today']): string | null {
  const s = today.split;
  if (!s) return null;
  const parts = ([['Dealers', s.dealer], ['Projects', s.project], ['Other', s.other]] as const).map(([label, part]) =>
    part.amount != null ? `${label} ${rm0(part.amount)}` : `${label} ${count(part.invoice_count)}`,
  );
  return parts.join(' · ');
}
