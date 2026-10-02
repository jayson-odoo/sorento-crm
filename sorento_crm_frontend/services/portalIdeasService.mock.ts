/**
 * Phase 1 mock for the public track page (PLAN-ideation-in-crm slice M5). In-memory, no network.
 *
 *   Valid token   : Ab3dEf9hJk2LmN0p  (the mobile-app idea, two comments)
 *   Anything else : unknown token, the page renders its not-found state
 */
import type { PortalIdea, PortalIdeaComment } from '@/types/ideas';

export const MOCK_VALID_PORTAL_TOKEN = 'Ab3dEf9hJk2LmN0p';

export class PortalIdeaNotFoundError extends Error {
  constructor() {
    super('This link is not valid.');
    this.name = 'PortalIdeaNotFoundError';
  }
}

const wait = (ms = 200) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const IDEA: PortalIdea = {
  title: 'I want a mobile app so field staff can log deliveries offline',
  ideaNumber: 'IDEA-0001',
  statusLabel: 'New',
  statusColor: 'info',
  submittedAt: '2026-07-20T06:19:00Z',
  submitterFirstName: 'WAWA',
  upvotes: 2,
};

let comments: PortalIdeaComment[] = [
  {
    id: 'pc-1',
    parentId: null,
    authorName: 'Admin',
    isSubmitter: false,
    body: 'Thanks for this. Offline capture with sync on reconnect is on our list to look at.',
    createdAt: '2026-07-21T01:05:00Z',
    deleted: false,
  },
  {
    id: 'pc-2',
    parentId: 'pc-1',
    authorName: 'WAWA',
    isSubmitter: true,
    body: 'Great, about 30 of our field staff use Android phones.',
    createdAt: '2026-07-21T06:30:00Z',
    deleted: false,
  },
];
let seq = 10;

function assertValid(token: string) {
  if (token !== MOCK_VALID_PORTAL_TOKEN) throw new PortalIdeaNotFoundError();
}

export async function getPortalIdea(token: string): Promise<PortalIdea> {
  await wait();
  assertValid(token);
  return IDEA;
}

export async function listPortalComments(token: string): Promise<PortalIdeaComment[]> {
  await wait();
  assertValid(token);
  return [...comments].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function postPortalComment(token: string, body: string): Promise<PortalIdeaComment> {
  await wait(300);
  assertValid(token);
  seq += 1;
  const created: PortalIdeaComment = {
    id: `pc-${seq}`,
    parentId: null,
    authorName: IDEA.submitterFirstName ?? 'You',
    isSubmitter: true,
    body: body.trim(),
    createdAt: new Date().toISOString(),
    deleted: false,
  };
  comments = [...comments, created];
  return created;
}
