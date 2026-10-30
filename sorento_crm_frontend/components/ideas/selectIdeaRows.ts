import type { Idea } from '@/types/ideas';

/**
 * Everything the Ideas list does to the loaded ideas, in one pure function: the Active | Archived
 * view, search, the Status picker, the Filters (submitter, channel, submitted range) and the sort.
 * Mirrors ss `select-idea-rows.ts` (ss main), which is also why the default order is votes
 * descending, then newest first.
 */
export interface IdeaRowQuery {
  search: string;
  view: 'active' | 'archived';
  /** Status LABELS, OR-ed; empty (or '') for every status. A lone string is one value. */
  status: string | string[];
  submitter: string | string[];
  channel: string | string[];
  /** `yyyy-MM-dd` bounds on the submitted date, inclusive; empty for open. */
  from: string;
  to: string;
  sort: { id: string; desc: boolean } | null;
}

const votes = (i: Idea): number => i.upvotes ?? 0;
const time = (iso: string): number => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
};
const title = (i: Idea): string => i.title ?? i.problem;

function compareBy(id: string, a: Idea, b: Idea): number {
  switch (id) {
    case 'votes':
      return votes(a) - votes(b);
    case 'submitted':
      return time(a.createdAt) - time(b.createdAt);
    case 'idea':
      return title(a).localeCompare(title(b));
    case 'submitter':
      return a.submitterName.localeCompare(b.submitterName);
    case 'channel':
      return String(a.source).localeCompare(String(b.source));
    case 'product':
      return a.productName.localeCompare(b.productName);
    case 'status':
      return a.statusLabel.localeCompare(b.statusLabel);
    default:
      return 0;
  }
}

function byVotes(a: Idea, b: Idea): number {
  return votes(b) - votes(a) || time(b.createdAt) - time(a.createdAt);
}

/** `yyyy-MM-dd` of an ISO timestamp in the reader's own zone, the zone the date column shows. */
function localDay(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const picked = (v: string | string[]): string[] => (typeof v === 'string' ? (v ? [v] : []) : v);

export function selectIdeaRows(ideas: Idea[], q: IdeaRowQuery): Idea[] {
  let rows = ideas.filter((r) =>
    q.view === 'archived' ? r.statusIsArchived : !r.statusIsArchived,
  );
  const needle = q.search.trim().toLowerCase();
  if (needle) {
    rows = rows.filter(
      (r) =>
        title(r).toLowerCase().includes(needle) ||
        r.problem.toLowerCase().includes(needle) ||
        r.submitterName.toLowerCase().includes(needle) ||
        r.productName.toLowerCase().includes(needle),
    );
  }
  const statuses = picked(q.status);
  const submitters = picked(q.submitter);
  const channels = picked(q.channel);
  if (statuses.length) rows = rows.filter((r) => statuses.includes(r.statusLabel));
  if (submitters.length) rows = rows.filter((r) => submitters.includes(r.submitterName));
  if (channels.length) rows = rows.filter((r) => channels.includes(String(r.source)));
  if (q.from) rows = rows.filter((r) => localDay(r.createdAt) >= q.from);
  if (q.to) rows = rows.filter((r) => localDay(r.createdAt) <= q.to);
  if (q.sort) {
    const dir = q.sort.desc ? -1 : 1;
    const id = q.sort.id;
    return [...rows].sort((a, b) => dir * compareBy(id, a, b) || byVotes(a, b));
  }
  return [...rows].sort(byVotes);
}
