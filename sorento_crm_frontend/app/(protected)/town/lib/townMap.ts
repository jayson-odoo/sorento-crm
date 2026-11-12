/**
 * The Town as a stylised map of Malaysia (TOWN-PROJECT-CITY, owner-approved mock v2, 11 Nov): the live island is
 * Selangor with Sorento HQ at Shah Alam; every other state is an island of its own, joined by causeways like the
 * live bridge. Schematic, not to scale: busy states get room. Plan:
 * documentation/plans/dashboard/PLAN-town-project-city-11nov.md.
 */
const DEG = Math.PI / 180;
/** The map frame is turned so the live port (bearing 232) faces west: Port Klang. */
const EX = -Math.cos(232 * DEG);
const EZ = -Math.sin(232 * DEG);
const NX = EZ;
const NZ = -EX;

/** Map units (east, north) to world (x, z); Shah Alam is the origin. */
export const mapXZ = (e: number, n: number): [number, number] => [e * EX + n * NX, e * EZ + n * NZ];

export interface StateDef {
  key: string;
  /** the `my_state` lookup value the snapshot sends */
  name: string;
  e: number;
  n: number;
  /** radii along and across `rot` (map degrees from east) */
  rx: number;
  ry: number;
  rot: number;
  /** the state its causeway comes from; none = reached by sea */
  parent?: string;
  /** for Selangor's neighbours: the high-street exit bearing on the live island */
  exit?: number;
}

export const STATES: StateDef[] = [
  { key: 'selangor', name: 'Selangor', e: 0, n: 0, rx: 27.6, ry: 27.6, rot: 0 },
  { key: 'kl', name: 'Kuala Lumpur', e: 46, n: 11, rx: 12, ry: 9.5, rot: 20, parent: 'selangor', exit: 44 },
  { key: 'putrajaya', name: 'Putrajaya', e: 35, n: -30, rx: 5.5, ry: 5, rot: 0, parent: 'selangor', exit: 92 },
  { key: 'perak', name: 'Perak', e: -36, n: 52, rx: 26, ry: 17, rot: 110, parent: 'selangor', exit: 287 },
  { key: 'penang', name: 'Pulau Pinang', e: -74, n: 84, rx: 7.5, ry: 6, rot: 80, parent: 'perak' },
  { key: 'kedah', name: 'Kedah', e: -38, n: 104, rx: 16, ry: 12, rot: 80, parent: 'perak' },
  { key: 'perlis', name: 'Perlis', e: -46, n: 128, rx: 6.5, ry: 6, rot: 60, parent: 'kedah' },
  { key: 'pahang', name: 'Pahang', e: 40, n: 48, rx: 25, ry: 19, rot: 50, parent: 'kl' },
  { key: 'terengganu', name: 'Terengganu', e: 68, n: 96, rx: 18, ry: 10, rot: 65, parent: 'pahang' },
  { key: 'kelantan', name: 'Kelantan', e: 36, n: 118, rx: 16, ry: 13, rot: 80, parent: 'terengganu' },
  { key: 'ns', name: 'Negeri Sembilan', e: 36, n: -58, rx: 13, ry: 11, rot: 30, parent: 'putrajaya' },
  { key: 'melaka', name: 'Melaka', e: 18, n: -80, rx: 8, ry: 7, rot: 30, parent: 'ns' },
  { key: 'johor', name: 'Johor', e: 68, n: -88, rx: 26, ry: 17, rot: 10, parent: 'ns' },
  { key: 'notset', name: 'State not set', e: -42, n: -58, rx: 8, ry: 7, rot: 0 },
  { key: 'sarawak', name: 'Sarawak', e: 205, n: -6, rx: 48, ry: 17, rot: 25 },
  { key: 'labuan', name: 'Labuan', e: 246, n: 56, rx: 4, ry: 4, rot: 0 },
  { key: 'sabah', name: 'Sabah', e: 282, n: 70, rx: 26, ry: 20, rot: 35 },
];

export const STATE_BY = Object.fromEntries(STATES.map((s) => [s.key, s])) as Record<string, StateDef>;
const BY_NAME = new Map(STATES.map((s) => [s.name.toLowerCase(), s.key]));

/** A snapshot's state (a `my_state` value) as a map key; blank or unknown is the "State not set" islet. */
export const stateKeyOf = (name: string | null | undefined): string => BY_NAME.get((name ?? '').trim().toLowerCase()) ?? 'notset';

export type SiteLook = 'plain' | 'before' | 'ground' | 'frame' | 'clad' | 'done';

/** How built-up a project site looks: the project's own launch -> delivery timeline (owner, 11 Nov), never our
 * sales stage. Either date missing, or delivery not after launch: a tidy prepared plot. */
export function siteLook(site: { launch_date: string | null; delivery_date: string | null }, day: string): SiteLook {
  if (!site.launch_date || !site.delivery_date) return 'plain';
  const l = Date.parse(site.launch_date);
  const d = Date.parse(site.delivery_date);
  const now = Date.parse(day);
  if (!(d > l)) return 'plain';
  if (now < l) return 'before';
  const k = (now - l) / (d - l);
  return k < 0.25 ? 'ground' : k < 0.6 ? 'frame' : k < 0.95 ? 'clad' : 'done';
}

/** A flag colour per seeded status key, used only when the CRM's status carries no colour of its own. */
const STAGE_COLORS: Record<string, number> = {
  identified: 0x9ca3af, registered: 0x2563eb, specified: 0x0d9488, quoted: 0xf59e0b, tendering: 0xea580c, po_received: 0x16a34a,
};
const GREY = 0x9ca3af;

/** Our sales stage as the CRM names it (the status row's label, sent with the site); a stage the snapshot
 * carries no label for reads as its key ("final_negotiation" -> "Final negotiation"). The flag only, never the building. */
export function stageLabel(site: { stage: string | null; stage_label?: string | null }): string {
  if (site.stage_label) return site.stage_label;
  if (!site.stage) return 'Stage not set';
  const words = site.stage.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The flag colour: the CRM status's own colour, else the default for a seeded key, else grey. */
export function stageColor(site: { stage: string | null; stage_color?: string | null }): number {
  if (site.stage_color && /^#[0-9a-f]{6}$/i.test(site.stage_color)) return parseInt(site.stage_color.slice(1), 16);
  return (site.stage && STAGE_COLORS[site.stage]) || GREY;
}

export const LOOK_WORDS: Record<SiteLook, string> = {
  plain: 'no dates yet', before: 'launching', ground: 'groundworks', frame: 'frame going up', clad: 'cladding', done: 'finished',
};

/** "Residensi Alpha · P-0101", or "Project site" when the viewer's variant carries no name. */
export const siteTitle = (site: { name?: string; code?: string | null }) =>
  site.name ? (site.code ? `${site.name} · ${site.code}` : site.name) : 'Project site';

// date-format-ok: a month-name table; "Mar 2025" straight from the ISO date, no time zone involved
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH = (iso: string) => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;

/** "Launch Mar 2025 · Delivery Mar 2028 · 56% of the way" (the project's own dates). */
export function siteTimeline(site: { launch_date: string | null; delivery_date: string | null }, day: string): string {
  const { launch_date: l, delivery_date: d } = site;
  if (!l && !d) return 'No launch date · no delivery date';
  if (!l) return `No launch date · delivery ${MONTH(d as string)}`;
  if (!d) return `Launch ${MONTH(l)} · no delivery date`;
  const span = Date.parse(d) - Date.parse(l);
  if (!(span > 0)) return `Launch ${MONTH(l)} · Delivery ${MONTH(d)}`;
  const k = Math.round(((Date.parse(day) - Date.parse(l)) / span) * 100);
  return `Launch ${MONTH(l)} · Delivery ${MONTH(d)} · ${k < 0 ? 'not launched yet' : `${Math.min(k, 100)}% of the way`}`;
}

/** A shop's map key. `state` missing altogether (a snapshot built before TOWN-PROJECT-CITY, served until the
 * next tick, e.g. overnight) keeps the shop on Selangor's high street, as the town always drew it; `null` is
 * a dealer whose state is not known: the "State not set" islet. */
export const shopStateKey = (state: string | null | undefined): string => (state === undefined ? 'selangor' : stateKeyOf(state));
