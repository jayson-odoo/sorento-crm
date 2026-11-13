/** WA-COMPLAINT-INTAKE B-3: the idea detail metadata shows Type with the label. Harness mirrors IdeaDetail.test.tsx. */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/ideas/idea-1',
  useSearchParams: () => new URLSearchParams(),
}));

// An admin-looking session: the Phase 1 fallback granted manage to this user. It must not.
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Pat Admin', roleName: 'Admin' } }, status: 'authenticated' }),
}));

const held = new Set<string>();
vi.mock('@/hooks/usePermissions', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, useHasPermission: (slug: string) => held.has(slug) };
});

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
    dismiss: vi.fn(),
  },
}));

vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'toast-1'),
  dismissDeferredToast: vi.fn(),
}));

const svc = vi.hoisted(() => ({
  getIdea: vi.fn(),
  listIdeas: vi.fn(),
  getMergedChildren: vi.fn(),
  listComments: vi.fn(),
  voteIdea: vi.fn(),
  updateIdea: vi.fn(),
  moveIdeaToStatus: vi.fn(),
  restoreIdea: vi.fn(),
  unmergeIdea: vi.fn(),
  mergeIdeas: vi.fn(),
  promoteIdea: vi.fn(),
  uploadAttachment: vi.fn(),
  fetchAttachment: vi.fn(),
  addComment: vi.fn(),
  editComment: vi.fn(),
  createIdea: vi.fn(),
  getBoard: vi.fn(),
  reorderIdeas: vi.fn(),
  getSimilarIdeas: vi.fn(),
  // The real helper's contract (AC-B-03), so a component that imports it still works under this mock.
  normalizeUseCases: (v: unknown) =>
    (Array.isArray(v) ? v : typeof v === 'string' ? v.split(/\r?\n/) : [])
      .map((x: unknown) => String(x).trim())
      .filter(Boolean),
  IDEA_STATUS_FILTER_OPTIONS: [{ value: 'archived', label: 'Archived' }],
}));
vi.mock('@/services/ideasService', () => svc);

const pending = vi.hoisted(() => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => pending);


import { IdeaDetail, IdeaDetailHeader } from './IdeaDetail';

function makeIdea(over: Record<string, unknown> = {}) {
  return {
    id: 'idea-1', productName: 'Sorento CRM', status: 'new', statusId: 'st-new', statusLabel: 'New',
    statusColor: 'info', statusIsArchived: false, transitions: [], advanceTransitionId: null,
    title: 'Faster quotes', problem: 'Quotes take too long to write', proposedSolution: null, impact: null,
    department: null, rawText: 'original words', source: 'whatsapp', submitterName: 'Jane Lim', upvotes: 3,
    myVote: null, priority: 1, rank: 1, attachments: [], createdAt: '2026-07-21T09:05:00Z',
    ideaNumber: 'IDEA-0042', mergedIntoId: null, mergedInto: null, mergedCount: 0, ...over,
  };
}

async function show(idea: Record<string, unknown>) {
  svc.getIdea.mockResolvedValue(idea);
  svc.listIdeas.mockResolvedValue([idea]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IdeaDetailHeader id="idea-1" />
      <IdeaDetail id="idea-1" />
    </QueryClientProvider>,
  );
  await screen.findByRole('heading', { name: 'IDEA-0042' });
}

beforeEach(() => {
  vi.clearAllMocks();
  held.clear();
  held.add('ideation.board.view');
  svc.getMergedChildren.mockResolvedValue([]);
  svc.listComments.mockResolvedValue([]);
  svc.getSimilarIdeas.mockResolvedValue({ available: true, ideas: [] });
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
});
afterEach(() => cleanup());

describe('B-3 detail metadata Type', () => {
  it('an issue shows "Type" and "Issue"', async () => {
    await show(makeIdea({ type: 'issue' }));
    expect(screen.getByText(/Type/)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/Type\s*:?\s*Issue/);
  });

  it('a feature request shows the Feature request label', async () => {
    await show(makeIdea({ type: 'idea' }));
    expect(document.body.textContent).toMatch(/Type\s*:?\s*Feature request/);
  });

  it('an idea with no type data reads Feature request', async () => {
    await show(makeIdea());
    expect(document.body.textContent).toMatch(/Type\s*:?\s*Feature request/);
  });
});
