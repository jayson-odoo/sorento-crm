/**
 * TOWN-PROJECT-CITY mock v2: the page around the forked live engine (townWorldMap.ts). The shell copies the live
 * TownScene markup and classes (stage, tooltip, icon buttons, legend); the lightbox copies the live Dialog look.
 * Mock only: every dealer, project, trading house, value and date in snapshot.json is invented.
 */
import { STATES, createTownRenderer, mountWorld, type WorldHandle } from './townWorldMap';
import fullSnapshot from './snapshot.json';

type Snap = typeof fullSnapshot & Record<string, unknown>;
type Variant = 'full' | 'redact' | 'wall';
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const del = (o: Record<string, unknown> | undefined, ...keys: string[]) => keys.forEach((k) => o && delete o[k]);

/** the variants the server sends: `redact()` for a viewer without sales.reports.view, `strip_names()` for the wallboard */
function variantOf(v: Variant): Snap {
  const s = clone(fullSnapshot) as Snap;
  const names = () => {
    s.shops.forEach((sh) => del(sh as never, 'name', 'code', 'today_amount', 'ninety_day_amount'));
    s.projects.sites.forEach((p) => del(p as never, 'name', 'code', 'estimated_value'));
    s.trading_houses.rows.forEach((r) => del(r as never, 'name'));
  };
  if (v === 'redact') {
    del(s.today as never, 'amount');
    del(s.compare as never, 'last_week_amount');
    Object.values(s.today.split).forEach((x) => del(x as never, 'amount'));
    s.shops.forEach((sh) => del(sh as never, 'rank'));
    names();
  }
  if (v === 'wall') names();
  return s;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>('c');
const stage = $('stage');
const labels = $('labels');
const tip = $('tip');
const renderer = createTownRenderer(canvas);
const view = { current: { yaw: (142 * Math.PI) / 180, tilt: Math.atan2(70, 80), zoom: 1 } };
const clock = { current: 0 };
const motion = { current: !matchMedia('(prefers-reduced-motion: reduce)').matches };
let variant: Variant = 'full';
let snap = variantOf(variant);
let world: WorldHandle | null = null;

const rm = (v?: string | null) => (v == null ? '' : `RM ${Number(v).toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
const STAGE: Record<string, string> = { identified: 'Identified', registered: 'Registered', specified: 'Spec In', quoted: 'Quoted', tendering: 'Tendering', po_received: 'PO Received' };
const MONTH = (d: string) => new Date(d).toLocaleDateString('en-MY', { month: 'short', year: 'numeric' });
const stateName = (k: string | null) => STATES.find((s) => s.key === (k ?? 'notset'))?.name ?? 'State not set';
function timeline(p: { launch_date: string | null; delivery_date: string | null }) {
  if (!p.launch_date && !p.delivery_date) return 'No launch date · no delivery date';
  if (!p.launch_date || !p.delivery_date) return p.launch_date ? `Launch ${MONTH(p.launch_date)} · no delivery date` : `No launch date · delivery ${MONTH(p.delivery_date as string)}`;
  const l = Date.parse(p.launch_date);
  const d = Date.parse(p.delivery_date);
  const k = Math.round(((Date.parse(snap.day) - l) / (d - l)) * 100);
  return `Launch ${MONTH(p.launch_date)} · Delivery ${MONTH(p.delivery_date)} · ${k < 0 ? 'not launched yet' : `${Math.min(k, 100)}% of the way`}`;
}

/* ---------------- lightbox: the live Dialog look ---------------- */
const box = $('box');
function show(title: string, meta: string, rows: [string, string][], link?: string) {
  $('boxTitle').textContent = title;
  $('boxMeta').textContent = meta;
  $('boxRows').innerHTML = rows.map(([k, v]) => `<tr class="border-b border-border last:border-0"><td class="py-1.5 pe-4 text-muted-foreground">${k}</td><td class="py-1.5 text-end font-medium tabular-nums">${v}</td></tr>`).join('');
  const a = $<HTMLAnchorElement>('boxLink');
  a.hidden = !link;
  a.textContent = link ?? '';
  box.hidden = false;
  (box.querySelector('button') as HTMLButtonElement).focus();
}
const closeBox = () => { box.hidden = true; };
box.addEventListener('click', (e) => { if (e.target === box) closeBox(); });
$('boxClose').addEventListener('click', closeBox);
addEventListener('keydown', (e) => { if (e.key === 'Escape') closeBox(); });

function select(target: { kind: string; key?: string }) {
  const full = variant === 'full';
  const s = snap;
  if (target.kind === 'site') {
    const p = s.projects.sites.find((x) => x.key === target.key) as (typeof s.projects.sites)[number] & { name?: string; code?: string; estimated_value?: string | null };
    if (!p) return;
    const rows: [string, string][] = [['Stage', STAGE[p.stage]], ['Final negotiation', p.final_negotiation ? 'Yes' : 'No'], ['State', stateName(p.state)], ['Timeline', timeline(p)]];
    if (p.estimated_value) rows.push(['Estimated value', rm(p.estimated_value)]);
    return show(p.name ? `${p.name} · ${p.code}` : 'Project site', `${STAGE[p.stage]}${p.final_negotiation ? ' · final negotiation' : ''}`, rows, p.name ? 'Open project' : undefined);
  }
  if (target.kind === 'trading_house') {
    const r = s.trading_houses.rows.find((x) => x.key === target.key) as (typeof s.trading_houses.rows)[number] & { name?: string };
    if (!r) return;
    return show(r.name ?? 'Trading house', r.today_docs ? 'Bought today (project invoice)' : 'No project invoice today', [['State', stateName(r.state)], ['Open projects it is on', String(r.open_projects)], ['Project invoices today', String(r.today_docs)]], r.name ? 'Open customer' : undefined);
  }
  if (target.kind === 'projects') {
    return show(`${s.projects.open_count} open projects`, `${s.projects.sites.length} on the map · +${s.projects.more} more · ${s.projects.dormant} dormant, not shown`, s.projects.sites.map((p) => [(p as { name?: string }).name ?? STAGE[p.stage], `${STAGE[p.stage]} · ${stateName(p.state)}`]));
  }
  if (target.kind === 'sales') {
    const sp = s.today.split as Record<string, { amount?: string; invoice_count: number }>;
    const v = (k: string) => (full ? rm(sp[k].amount) : `${sp[k].invoice_count} invoices`);
    return show("Today's sales", 'Same figure as the sales report', [...(full ? ([['Invoiced today', rm((s.today as { amount?: string }).amount)]] as [string, string][]) : []), ['Dealers', v('dealer')], ['Projects', v('project')], ['Other', v('other')], ['Invoices', String(s.today.invoice_count)]], full ? 'Open sales report' : undefined);
  }
  if (target.kind === 'shop') {
    const sh = s.shops.find((x) => x.key === target.key) as (typeof s.shops)[number] & { name?: string; today_amount?: string };
    if (!sh) return;
    return show(sh.name ?? (sh.account_label ? `Dealer ${sh.account_label}` : 'Dealer'), sh.today_docs ? 'Bought today' : 'No invoice today', [['State', stateName((sh as { state?: string | null }).state ?? null)], ['Invoices today', String(sh.today_docs)], ...(sh.today_amount ? ([['Invoiced today', rm(sh.today_amount)]] as [string, string][]) : [])]);
  }
  const words: Record<string, string> = { deliver: 'Lorries: sales orders due today or overdue', low: 'Products below their reorder level', approve: 'Waiting for a decision', port: 'Open shipments from overseas suppliers', bought: 'Dealers invoiced today' };
  show(target.kind[0].toUpperCase() + target.kind.slice(1), words[target.kind] ?? '', []);
}

/* ---------------- the world ---------------- */
function mount(intro: boolean) {
  world?.dispose();
  world = mountWorld({
    canvas, stage, labelLayer: labels, renderer, snapshot: snap as never, prev: null, beat: null, intro, reduced: !motion.current,
    motion, view, clock,
    select: (t) => select(t as never),
    hover: (h) => {
      tip.hidden = !h;
      if (!h) return;
      (tip.children[0] as HTMLElement).textContent = h.title;
      (tip.children[1] as HTMLElement).textContent = h.detail;
      tip.style.left = `${h.x}px`;
      tip.style.top = `${h.y - 12}px`;
    },
  });
  (window as unknown as { world: WorldHandle }).world = world;
}
// `?still` skips the fly-in (screenshots in a slow headless browser)
mount(!new URLSearchParams(location.search).has('still'));

$('zoomOut').addEventListener('click', () => world?.zoom(-1));
$('zoomIn').addEventListener('click', () => world?.zoom(1));
$('reset').addEventListener('click', () => world?.reset());
$('whole').addEventListener('click', () => world?.flyTo('all'));
const motionBtn = $('motion');
const setMotionIcon = () => {
  motionBtn.setAttribute('aria-label', motion.current ? 'Pause motion' : 'Play motion');
  motionBtn.title = motion.current ? 'Pause motion' : 'Play motion';
  motionBtn.innerHTML = motion.current ? ICON.pause : ICON.play;
};
motionBtn.addEventListener('click', () => { world?.setMotion(!motion.current); setMotionIcon(); });

/* state chips: one per state with something on it, then the rest; a chip flies the camera there */
const chips = $('chips');
const busy = (k: string) => snap.shops.some((s) => ((s as { state?: string | null }).state ?? 'notset') === k) || snap.projects.sites.some((p) => (p.state ?? 'notset') === k) || snap.trading_houses.rows.some((r) => (r.state ?? 'notset') === k);
[...STATES].sort((a, b) => Number(busy(b.key)) - Number(busy(a.key))).forEach((d) => {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `shrink-0 rounded-full border border-border px-2.5 py-0.5 text-xs font-medium hover:bg-accent ${busy(d.key) ? 'bg-background text-foreground' : 'bg-transparent text-muted-foreground'}`;
  b.textContent = d.name;
  b.addEventListener('click', () => world?.flyTo(d.key));
  chips.appendChild(b);
});

/* mock control: the three variants */
document.querySelectorAll<HTMLButtonElement>('[data-variant]').forEach((b) =>
  b.addEventListener('click', () => {
    variant = b.dataset.variant as Variant;
    document.querySelectorAll<HTMLButtonElement>('[data-variant]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    snap = variantOf(variant);
    closeBox();
    mount(false);
  }),
);

const ICON = {
  pause: '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/></svg>',
  play: '<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>',
};
setMotionIcon();
(window as unknown as { mock: unknown }).mock = { select };
