/**
 * Phase 1 mock for the Ideas gateway (PLAN-ideation-in-crm slice M). In-memory, per page load,
 * no network. `ideasService.ts` delegates here until Phase 2 swaps each function for the
 * `/api/v1/ideation/*` call named in its doc comment.
 *
 * How each header state of the idea page is reached (mock section 2):
 *   A  Draft, next move "Move to New"        : "I wish the CRM could remind me before a DO SLA breaches"
 *   B  Voted, next move "Move to Triaged"    : "Let CS bulk-export orders to Excel with column presets"
 *   C  Closed, no next move, Edit is primary : "E2E Idea 20260928-1349 Bravo - problem statement"
 *   D  Archived, primary Restore             : "a brand new test idea about export scheduling"
 *   E  Merged child, primary Unmerge         : "Remind me before a DO SLA breaches"
 * Promote to BR is refused with ss's 403 message for ideas whose department is Customer Service
 * (the "Let CS bulk-export" idea); every other idea promotes.
 */
import type {
  Idea,
  IdeaAttachment,
  IdeaBoard,
  IdeaComment,
  IdeaCreateInput,
  IdeaListParams,
  IdeaMergeInput,
  IdeaPromoteInput,
  IdeaStatusColor,
  IdeaTransition,
  IdeaUpdateInput,
} from '@/types/ideas';

const wait = (ms = 160) => new Promise<void>((resolve) => setTimeout(resolve, ms));

interface StatusRow {
  id: string;
  key: string;
  label: string;
  color: IdeaStatusColor;
  isArchived: boolean;
  onBoard: boolean;
}

const STATUSES: StatusRow[] = [
  { id: 's-draft', key: 'draft', label: 'Draft', color: 'grey', isArchived: false, onBoard: false },
  { id: 's-new', key: 'new', label: 'New', color: 'info', isArchived: false, onBoard: true },
  { id: 's-triaged', key: 'triaged', label: 'Triaged', color: 'primary', isArchived: false, onBoard: true },
  { id: 's-linked', key: 'linked', label: 'Linked', color: 'warning', isArchived: false, onBoard: true },
  { id: 's-building', key: 'building', label: 'Building', color: 'warning', isArchived: false, onBoard: true },
  { id: 's-delivered', key: 'delivered', label: 'Delivered', color: 'success', isArchived: false, onBoard: true },
  { id: 's-closed', key: 'closed', label: 'Closed', color: 'grey', isArchived: false, onBoard: false },
  { id: 's-archived', key: 'archived', label: 'Archived', color: 'grey', isArchived: true, onBoard: false },
];

const byKey = (key: string) => STATUSES.find((s) => s.key === key) as StatusRow;

/** The status filter's options (ss `GET /embed/ideas` filter keys). */
export const IDEA_STATUS_FILTER_OPTIONS = STATUSES.map((s) => ({ value: s.key, label: s.label }));

function transitionsFor(status: string): IdeaTransition[] {
  const make = (to: StatusRow): IdeaTransition => ({
    id: `t-${status}-${to.key}`,
    label: `Move to ${to.label}`,
    toStatusId: to.id,
    toStatusLabel: to.label,
  });
  // The lifecycle graph: forward one step at a time, back where a triager might reconsider.
  const GRAPH: Record<string, string[]> = {
    draft: ['new'],
    new: ['triaged'],
    triaged: ['linked', 'new'],
    linked: ['building'],
    building: ['delivered'],
    delivered: ['closed'],
  };
  return (GRAPH[status] ?? []).map((k) => make(byKey(k)));
}

/** The next status by the tenant's sort order. */
const ADVANCE_TO: Record<string, string> = {
  draft: 'new',
  new: 'triaged',
  triaged: 'linked',
  linked: 'building',
  building: 'delivered',
  delivered: 'closed',
};

function withStatus(idea: Idea, key: string): Idea {
  const row = byKey(key);
  const transitions = transitionsFor(key);
  const advanceKey = ADVANCE_TO[key];
  return {
    ...idea,
    status: row.key,
    statusId: row.id,
    statusLabel: row.label,
    statusColor: row.color,
    statusIsArchived: row.isArchived,
    transitions,
    advanceTransitionId: transitions.find((t) => t.toStatusId === byKey(advanceKey ?? '')?.id)?.id ?? null,
  };
}

let ideaSeq = 100;
let commentSeq = 100;
let attachmentSeq = 100;

function seed(
  partial: Pick<Idea, 'id' | 'title' | 'problem' | 'submitterName' | 'createdAt'> &
    Partial<Idea> & { statusKey: string },
): Idea {
  const { statusKey, ...rest } = partial;
  const base: Idea = {
    productName: 'Sorento CRM',
    status: 'new',
    statusId: '',
    statusLabel: '',
    statusColor: 'info',
    statusIsArchived: false,
    transitions: [],
    advanceTransitionId: null,
    proposedSolution: null,
    impact: null,
    department: null,
    rawText: partial.problem,
    source: 'whatsapp',
    upvotes: 0,
    myVote: null,
    priority: 0,
    rank: null,
    attachments: [],
    ideaNumber: null,
    mergedIntoId: null,
    mergedInto: null,
    mergedCount: 0,
    businessRequirements: [],
    ...rest,
  };
  return withStatus(base, statusKey);
}

let ideas: Idea[] = [
  seed({
    id: 'idea-mobile',
    ideaNumber: 'IDEA-0001',
    title: 'I want a mobile app so field staff can log deliveries offline',
    problem: 'I want a mobile app so field staff can log deliveries offline',
    proposedSolution: 'a mobile app so field staff can log deliveries offline',
    impact: 'it saves 2 hours a day',
    department: 'Operations',
    rawText:
      'I want a mobile app so field staff can log deliveries offline. It would be a mobile app, it saves 2 hours a day.',
    submitterName: 'WAWA',
    createdAt: '2026-07-20T06:19:00Z',
    statusKey: 'new',
    upvotes: 2,
    priority: 1,
    attachments: [
      { id: 'att-1', kind: 'audio', name: 'Voice note from WAWA.ogg', sizeBytes: 48200, durationSec: 14 },
      { id: 'att-2', kind: 'image', name: 'basement-signal.jpg', sizeBytes: 2457600, durationSec: null },
    ],
    businessRequirements: [
      { id: 'br-1', title: 'Offline delivery logging', statusLabel: 'Draft', statusColor: 'grey' },
    ],
  }),
  seed({
    id: 'idea-draft',
    ideaNumber: 'IDEA-0002',
    title: 'I wish the CRM could remind me before a DO SLA breaches',
    problem: 'I wish the CRM could remind me before a DO SLA breaches',
    submitterName: 'WAWA',
    createdAt: '2026-07-21T03:02:00Z',
    statusKey: 'draft',
  }),
  seed({
    id: 'idea-export',
    ideaNumber: 'IDEA-0003',
    title: 'Let CS bulk-export orders to Excel with column presets',
    problem: 'Let CS bulk-export orders to Excel with column presets',
    proposedSolution: 'An export button on the orders list that remembers the chosen columns',
    impact: 'CS stops rebuilding the same sheet every Monday',
    department: 'Customer Service',
    submitterName: 'Aisyah',
    createdAt: '2026-07-22T01:40:00Z',
    statusKey: 'new',
    upvotes: 2,
    myVote: 'up',
    priority: 2,
  }),
  seed({
    id: 'idea-sla-child',
    ideaNumber: 'IDEA-0004',
    title: 'Remind me before a DO SLA breaches',
    problem: 'Remind me before a DO SLA breaches',
    submitterName: 'Hafiz',
    createdAt: '2026-07-23T08:10:00Z',
    statusKey: 'new',
    mergedIntoId: 'idea-sla',
    mergedInto: { id: 'idea-sla', ideaNumber: 'IDEA-0006', title: 'SLA breach reminders on delivery orders' },
  }),
  seed({
    id: 'idea-closed',
    ideaNumber: 'IDEA-0005',
    title: 'E2E Idea 20260928-1349 Bravo - problem statement',
    problem: 'E2E Idea 20260928-1349 Bravo - problem statement',
    submitterName: 'Demo User',
    source: 'manual',
    createdAt: '2026-09-28T05:49:00Z',
    statusKey: 'closed',
  }),
  seed({
    id: 'idea-sla',
    ideaNumber: 'IDEA-0006',
    title: 'SLA breach reminders on delivery orders',
    problem: 'Dispatchers only find out a delivery order breached its SLA after the customer calls',
    proposedSolution: 'Notify the dispatcher an hour before the SLA clock runs out',
    impact: 'Fewer late deliveries and fewer angry calls',
    department: 'Operations',
    submitterName: 'Wei Ling',
    createdAt: '2026-07-19T02:30:00Z',
    statusKey: 'triaged',
    upvotes: 3,
    priority: 3,
    mergedCount: 1,
  }),
  seed({
    id: 'idea-archived',
    ideaNumber: 'IDEA-0007',
    title: 'a brand new test idea about export scheduling',
    problem: 'a brand new test idea about export scheduling',
    submitterName: 'Demo User',
    source: 'manual',
    createdAt: '2026-09-01T04:00:00Z',
    statusKey: 'archived',
  }),
  seed({
    id: 'idea-test',
    ideaNumber: 'IDEA-0008',
    title: 'test',
    problem: 'test',
    submitterName: 'Demo User',
    source: 'manual',
    createdAt: '2026-09-15T07:00:00Z',
    statusKey: 'new',
    upvotes: 1,
    myVote: 'up',
    priority: 4,
  }),
  seed({
    id: 'idea-delivered',
    ideaNumber: 'IDEA-0009',
    title: 'Show the dealer tier on the order confirmation',
    problem: 'Dealers cannot see which tier price they were given on the order confirmation',
    department: 'Sales',
    submitterName: 'Farid',
    createdAt: '2026-06-02T09:00:00Z',
    statusKey: 'delivered',
    upvotes: 5,
    priority: 5,
  }),
];

const CURRENT_USER = 'Demo User';

const commentsByIdea: Record<string, IdeaComment[]> = {
  'idea-mobile': [
    {
      id: 'c-1',
      parentId: null,
      authorName: 'Admin User',
      authorIsMe: false,
      body: 'Drivers lose signal in the Shah Alam warehouse basement. Offline capture with sync on reconnect would cover it.',
      createdAt: '2026-07-21T01:05:00Z',
      editedAt: null,
      deleted: false,
    },
    {
      id: 'c-2',
      parentId: 'c-1',
      authorName: 'Event Manager',
      authorIsMe: false,
      body: 'Same for the event crew at venues. Proof-of-delivery photo would help too.',
      createdAt: '2026-07-21T03:40:00Z',
      editedAt: null,
      deleted: false,
    },
    {
      id: 'c-3',
      parentId: null,
      authorName: CURRENT_USER,
      authorIsMe: true,
      body: 'Asked WAWA on WhatsApp: about 30 field staff, Android phones.',
      createdAt: '2026-07-22T08:12:00Z',
      editedAt: '2026-07-22T08:20:00Z',
      deleted: false,
    },
    {
      id: 'c-4',
      parentId: null,
      authorName: 'Admin User',
      authorIsMe: false,
      body: '',
      createdAt: '2026-07-22T09:30:00Z',
      editedAt: null,
      deleted: true,
    },
    {
      id: 'c-5',
      parentId: 'c-4',
      authorName: CURRENT_USER,
      authorIsMe: true,
      body: 'Thanks, noted.',
      createdAt: '2026-07-23T02:02:00Z',
      editedAt: null,
      deleted: false,
    },
  ],
};

function find(id: string): Idea {
  const idea = ideas.find((i) => i.id === id);
  if (!idea) throw new Error('Idea not found');
  return idea;
}

function put(next: Idea): Idea {
  ideas = ideas.map((i) => (i.id === next.id ? next : i));
  return next;
}

function matches(idea: Idea, { query, status }: IdeaListParams): boolean {
  if (status) {
    if (idea.status !== status) return false;
  } else if (idea.statusIsArchived) {
    return false;
  }
  const q = query?.trim().toLowerCase();
  if (!q) return true;
  return [idea.title, idea.problem, idea.submitterName, idea.ideaNumber, idea.department]
    .filter(Boolean)
    .some((v) => String(v).toLowerCase().includes(q));
}

export async function listIdeas(params: IdeaListParams): Promise<Idea[]> {
  await wait();
  return ideas.filter((i) => matches(i, params));
}

export async function getIdea(id: string): Promise<Idea> {
  await wait();
  return find(id);
}

export async function getBoard(): Promise<IdeaBoard> {
  await wait();
  const columns = STATUSES.filter((s) => s.onBoard).map((s) => ({
    statusId: s.id,
    key: s.key,
    title: s.label,
    color: s.color,
    ideas: ideas
      .filter((i) => i.status === s.key && !i.mergedIntoId)
      .sort((a, b) => a.priority - b.priority),
  }));
  return { columns };
}

export async function getMergedChildren(id: string): Promise<Idea[]> {
  await wait();
  return ideas.filter((i) => i.mergedIntoId === id);
}

export async function createIdea(input: IdeaCreateInput): Promise<Idea> {
  await wait(300);
  ideaSeq += 1;
  const created = seed({
    id: `idea-${ideaSeq}`,
    ideaNumber: `IDEA-${String(ideaSeq).padStart(4, '0')}`,
    title: input.problem.trim().slice(0, 80),
    problem: input.problem.trim(),
    proposedSolution: input.proposedSolution?.trim() || null,
    impact: input.impact?.trim() || null,
    department: input.department?.trim() || null,
    submitterName: CURRENT_USER,
    source: 'manual',
    createdAt: new Date().toISOString(),
    statusKey: 'new',
    priority: ideas.length + 1,
  });
  ideas = [created, ...ideas];
  for (const file of input.files ?? []) {
    await uploadAttachment(created.id, file);
  }
  return find(created.id);
}

export async function updateIdea(id: string, input: IdeaUpdateInput): Promise<Idea> {
  await wait();
  const idea = find(id);
  return put({ ...idea, ...input, title: input.problem ? input.problem.slice(0, 80) : idea.title });
}

export async function voteIdea(id: string): Promise<Idea> {
  await wait(120);
  const idea = find(id);
  if (idea.mergedIntoId) throw new Error('Votes are closed on a merged idea.');
  const voted = idea.myVote === 'up';
  return put({ ...idea, myVote: voted ? null : 'up', upvotes: idea.upvotes + (voted ? -1 : 1) });
}

export async function moveIdeaToStatus(id: string, toStatusId: string): Promise<Idea> {
  await wait();
  const idea = find(id);
  const transition = idea.transitions.find((t) => t.toStatusId === toStatusId);
  if (!transition) throw new Error('This idea cannot move to that status.');
  const target = STATUSES.find((s) => s.id === toStatusId) as StatusRow;
  void transition;
  return put(withStatus(idea, target.key));
}

export async function restoreIdea(id: string): Promise<Idea> {
  await wait();
  return put(withStatus(find(id), 'new'));
}

export async function archiveIdea(id: string): Promise<Idea> {
  await wait();
  return put(withStatus(find(id), 'archived'));
}

export async function deleteIdea(id: string): Promise<void> {
  await wait();
  find(id);
  ideas = ideas.filter((i) => i.id !== id);
  delete commentsByIdea[id];
}

export async function reorderIdeas(orderedIds: string[]): Promise<void> {
  await wait(100);
  const rank = new Map(orderedIds.map((id, index) => [id, index + 1]));
  ideas = ideas.map((i) => (rank.has(i.id) ? { ...i, priority: rank.get(i.id) as number } : i));
}

export async function mergeIdeas({ survivorId, ideaIds }: IdeaMergeInput): Promise<Idea> {
  await wait(300);
  const survivor = find(survivorId);
  const children = ideaIds.filter((id) => id !== survivorId);
  if (children.length === 0) throw new Error('Pick the idea to merge into.');
  const ref = { id: survivor.id, ideaNumber: survivor.ideaNumber, title: survivor.title };
  for (const childId of children) {
    put({ ...find(childId), mergedIntoId: survivor.id, mergedInto: ref });
  }
  return put({ ...find(survivorId), mergedCount: survivor.mergedCount + children.length });
}

export async function unmergeIdea(id: string): Promise<Idea> {
  await wait(300);
  const child = find(id);
  if (child.mergedIntoId) {
    const survivor = find(child.mergedIntoId);
    put({ ...survivor, mergedCount: Math.max(0, survivor.mergedCount - 1) });
  }
  return put({ ...child, mergedIntoId: null, mergedInto: null });
}

export async function promoteIdea(id: string, input: IdeaPromoteInput): Promise<Idea> {
  await wait(350);
  const idea = find(id);
  if (idea.department === 'Customer Service') {
    throw new Error('This user has no Business Requirements access in the Ideas workspace.');
  }
  return put({
    ...idea,
    businessRequirements: [
      ...idea.businessRequirements,
      { id: `br-${Date.now()}`, title: input.title, statusLabel: 'Draft', statusColor: 'grey' },
    ],
  });
}

export async function uploadAttachment(id: string, file: File): Promise<IdeaAttachment> {
  await wait(250);
  const idea = find(id);
  attachmentSeq += 1;
  const kind: IdeaAttachment['kind'] = file.type.startsWith('image/')
    ? 'image'
    : file.type.startsWith('audio/')
      ? 'audio'
      : file.type.startsWith('video/')
        ? 'video'
        : 'file';
  const attachment: IdeaAttachment = {
    id: `att-${attachmentSeq}`,
    kind,
    name: file.name,
    sizeBytes: file.size,
    durationSec: null,
  };
  put({ ...idea, attachments: [...idea.attachments, attachment] });
  return attachment;
}

// ---- comments ---------------------------------------------------------------------------

export async function listComments(ideaId: string): Promise<IdeaComment[]> {
  await wait();
  return [...(commentsByIdea[ideaId] ?? [])].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function addComment(
  ideaId: string,
  input: { body: string; parentId?: string | null },
): Promise<IdeaComment> {
  await wait(200);
  if (find(ideaId).mergedIntoId) throw new Error('Comments are closed on a merged idea.');
  const list = commentsByIdea[ideaId] ?? [];
  // A reply to a reply attaches to the same top-level comment (one level).
  const parent = list.find((c) => c.id === input.parentId);
  commentSeq += 1;
  const created: IdeaComment = {
    id: `c-${commentSeq}`,
    parentId: parent ? (parent.parentId ?? parent.id) : null,
    authorName: CURRENT_USER,
    authorIsMe: true,
    body: input.body.trim(),
    createdAt: new Date().toISOString(),
    editedAt: null,
    deleted: false,
  };
  commentsByIdea[ideaId] = [...list, created];
  return created;
}

export async function editComment(ideaId: string, commentId: string, body: string): Promise<IdeaComment> {
  await wait(160);
  const list = commentsByIdea[ideaId] ?? [];
  const target = list.find((c) => c.id === commentId);
  if (!target) throw new Error('Comment not found');
  const next = { ...target, body: body.trim(), editedAt: new Date().toISOString() };
  commentsByIdea[ideaId] = list.map((c) => (c.id === commentId ? next : c));
  return next;
}

export async function deleteComment(ideaId: string, commentId: string): Promise<void> {
  await wait(160);
  const list = commentsByIdea[ideaId] ?? [];
  const target = list.find((c) => c.id === commentId);
  if (!target) return;
  const hasReplies = list.some((c) => c.parentId === commentId);
  let next = hasReplies
    ? list.map((c) => (c.id === commentId ? { ...c, deleted: true, body: '' } : c))
    : list.filter((c) => c.id !== commentId);
  // A deleted placeholder with no replies left goes too.
  const parentId = target.parentId;
  if (!hasReplies && parentId) {
    const parent = next.find((c) => c.id === parentId);
    if (parent?.deleted && !next.some((c) => c.parentId === parentId)) {
      next = next.filter((c) => c.id !== parentId);
    }
  }
  commentsByIdea[ideaId] = next;
}
