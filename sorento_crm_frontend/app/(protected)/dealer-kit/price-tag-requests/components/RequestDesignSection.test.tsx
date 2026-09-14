/**
 * The CRM Design section (r9 S1/D3 + S2/D6, AC-S1-2 / AC-S2-5 / AC-S5-6).
 *
 * Marketing used to have to load the whole Konva editor to answer "is this the
 * one the salesperson is asking about". The section draws the DRAFT with the
 * salesperson's pins over it and a Done toggle per pin, so a round of changes
 * is worked off one list rather than a paragraph of prose.
 *
 * The one that matters most: viewing a version must draw THAT VERSION's
 * document. Phase 1 drew the current one under the version's title, which is
 * worse than not offering View at all - it says "this is what v1 looked like"
 * over something that is not.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const toasts = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../../services/priceTagRequestService', () => ({
  getRequestDesignPayload: vi.fn(),
}));

vi.mock('../../services/priceTagReviewService', () => ({
  listReviewComments: vi.fn(),
  setReviewCommentResolved: vi.fn(),
}));

vi.mock('../../services/priceTagDataService', () => ({
  getRequestVersion: vi.fn(),
  listRequestVersions: vi.fn(),
  restoreRequestVersion: vi.fn(),
}));

// The sheet renderer needs a browser; the card and the lightbox have their own
// suites. Here the section's own wiring is what is under test.
vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: (props: {
    payload: unknown;
    loading?: boolean;
    emptyMessage?: string;
    headerActions?: React.ReactNode;
    footer?: React.ReactNode;
    review?: { comments: unknown[]; currentRound?: number };
  }) => (
    <div data-testid="design-viewer">
      {props.loading && <span>loading</span>}
      {!props.loading && !props.payload && <span>{props.emptyMessage}</span>}
      <span data-testid="review-comment-count">
        {props.review?.comments.length ?? 0}
      </span>
      <span data-testid="review-current-round">
        {props.review?.currentRound ?? ''}
      </span>
      {props.headerActions}
      {props.footer}
    </div>
  ),
}));

vi.mock('@/components/dealer-kit/DesignLightbox', () => ({
  __esModule: true,
  default: (props: { title: string; payload: { version: number } }) => (
    <div data-testid="version-lightbox" data-version={props.payload?.version}>
      {props.title}
    </div>
  ),
}));

import { getRequestDesignPayload } from '../../services/priceTagRequestService';
import {
  listReviewComments,
  setReviewCommentResolved,
} from '../../services/priceTagReviewService';
import {
  getRequestVersion,
  listRequestVersions,
  restoreRequestVersion,
} from '../../services/priceTagDataService';
import RequestDesignSection from './RequestDesignSection';

const mockPayload = vi.mocked(getRequestDesignPayload);
const mockList = vi.mocked(listReviewComments);
const mockResolve = vi.mocked(setReviewCommentResolved);
const mockVersions = vi.mocked(listRequestVersions);
const mockRestore = vi.mocked(restoreRequestVersion);
const mockGetVersion = vi.mocked(getRequestVersion);

function payload(version = 7) {
  return {
    page_id: 'page-1',
    version,
    source: 'draft' as const,
    doc: {
      kind: 'tag_sheet',
      imposition: { page_width_mm: 210, page_height_mm: 297 },
      sheets: [{ id: 'sheet-1', tags: [] }],
    },
    resolvedData: {},
    assets: {},
    images: {},
    fonts: [],
  } as never;
}

function comment(overrides: Record<string, unknown> = {}) {
  return {
    id: 'comment-1',
    request_id: 'req-1',
    line_id: 'line-1',
    round: 1,
    x: 0.25,
    y: 0.5,
    w: 0,
    h: 0,
    body: 'Make the price bigger',
    author_name: 'ZZT Sales Sam',
    created_at: '2026-09-14T00:00:00Z',
    resolved_at: null,
    resolved_by_name: null,
    ...overrides,
  } as never;
}

function renderSection(currentRound?: number) {
  return render(
    <RequestDesignSection
      requestId="req-1"
      docNumber="PT-202609-0001"
      lineLabels={new Map([['line-1', 'ZZT-SINK-1']])}
      currentRound={currentRound}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPayload.mockResolvedValue(payload());
  mockList.mockResolvedValue([]);
  mockVersions.mockResolvedValue([]);
  // The live design is version 7; a version read answers its OWN document.
  mockGetVersion.mockResolvedValue(payload(1));
});

describe('loading the design (AC-S1-2)', () => {
  it('asks for the payload once per request', async () => {
    renderSection();

    await waitFor(() => expect(mockPayload).toHaveBeenCalledWith('req-1'));
    expect(mockPayload).toHaveBeenCalledTimes(1);
  });

  it('shows the empty state, and what to do next, when there is no design', async () => {
    mockPayload.mockResolvedValue(null as never);
    renderSection();

    expect(await screen.findByText('No design yet')).toBeInTheDocument();
  });

  it('a failed load is the empty state, not a broken card', async () => {
    mockPayload.mockRejectedValue(new Error('boom'));
    renderSection();

    expect(await screen.findByText('No design yet')).toBeInTheDocument();
  });
});

describe('the change request list (AC-S2-5)', () => {
  it('names each pin by its line code, its round and its author', async () => {
    mockList.mockResolvedValue([comment()]);
    renderSection();

    expect(await screen.findByText('Make the price bigger')).toBeInTheDocument();
    expect(
      screen.getByText(/ZZT-SINK-1 \/ round 1 \/ ZZT Sales Sam/),
    ).toBeInTheDocument();
  });

  it('a general comment is labelled General rather than given a tag', async () => {
    mockList.mockResolvedValue([
      comment({ id: 'c2', line_id: null, x: null, y: null, body: 'Too busy' }),
    ]);
    renderSection();

    expect(await screen.findByText(/General \/ round 1/)).toBeInTheDocument();
  });

  it('Done resolves the comment and re-reads the list', async () => {
    mockList.mockResolvedValueOnce([comment()]);
    mockResolve.mockResolvedValue(comment({ resolved_at: '2026-09-14T02:00:00Z' }));
    mockList.mockResolvedValueOnce([
      comment({ resolved_at: '2026-09-14T02:00:00Z', resolved_by_name: 'Mei' }),
    ]);
    renderSection();
    await screen.findByText('Make the price bigger');

    fireEvent.click(screen.getByRole('button', { name: /Done/ }));

    await waitFor(() =>
      expect(mockResolve).toHaveBeenCalledWith('req-1', 'comment-1', true),
    );
    expect(await screen.findByRole('button', { name: /Reopen/ })).toBeInTheDocument();
  });

  it('Reopen puts it back', async () => {
    mockList.mockResolvedValue([
      comment({ resolved_at: '2026-09-14T02:00:00Z', resolved_by_name: 'Mei' }),
    ]);
    mockResolve.mockResolvedValue(comment());
    renderSection();
    await screen.findByText('Make the price bigger');

    fireEvent.click(screen.getByRole('button', { name: /Reopen/ }));

    await waitFor(() =>
      expect(mockResolve).toHaveBeenCalledWith('req-1', 'comment-1', false),
    );
  });

  it('a failed toggle says so rather than lying about the state', async () => {
    mockList.mockResolvedValue([comment()]);
    mockResolve.mockRejectedValue(new Error('403'));
    renderSection();
    await screen.findByText('Make the price bigger');

    fireEvent.click(screen.getByRole('button', { name: /Done/ }));

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        'Could not update the change request',
      ),
    );
  });

  it('hands the same comments to the overlay so the list and the pins agree', async () => {
    mockList.mockResolvedValue([comment(), comment({ id: 'c2' })]);
    renderSection();

    await waitFor(() =>
      expect(screen.getByTestId('review-comment-count')).toHaveTextContent('2'),
    );
  });

  it('there is no list at all when nobody has asked for a change', async () => {
    renderSection();
    await waitFor(() => expect(mockList).toHaveBeenCalled());

    expect(screen.queryByText('Change requests')).toBeNull();
  });

  it('passes currentRound to the pin layer so an earlier-round pin can render grey (review-round leftover)', async () => {
    mockList.mockResolvedValue([comment()]);
    renderSection(2);

    await waitFor(() =>
      expect(screen.getByTestId('review-current-round')).toHaveTextContent('2'),
    );
  });
});

describe('History (AC-S5-6)', () => {
  it('opens the versions sheet from the section header', async () => {
    mockVersions.mockResolvedValue([
      {
        version: 2,
        commit_message: 'Marked proof ready',
        created_by_name: 'Mei',
        created_at: '2026-09-14T00:00:00Z',
      },
    ]);
    renderSection();

    fireEvent.click(await screen.findByRole('button', { name: /History/ }));

    await waitFor(() => expect(mockVersions).toHaveBeenCalledWith('req-1'));
    expect(await screen.findByText('Version 2')).toBeInTheDocument();
  });

  it('Restore writes the version back and reloads the drawn design', async () => {
    mockVersions.mockResolvedValue([
      {
        version: 1,
        commit_message: null,
        created_by_name: 'Mei',
        created_at: '2026-09-12T00:00:00Z',
      },
    ]);
    mockRestore.mockResolvedValue({
      version: 3,
      commit_message: 'Restored v1',
      created_by_name: 'Mei',
      created_at: '2026-09-14T04:00:00Z',
    });
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: /History/ }));
    const row = await screen.findByTestId('request-version-1');

    fireEvent.click(within(row).getByRole('button', { name: /Restore/ }));

    await waitFor(() => expect(mockRestore).toHaveBeenCalledWith('req-1', 1));
    // The canvas has to reflect it: a restore that leaves the old document on
    // screen reads as a restore that did not happen.
    await waitFor(() => expect(mockPayload).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith('Restored v1'));
  });

  it('View draws THAT version, not the current design under its name', async () => {
    mockVersions.mockResolvedValue([
      {
        version: 1,
        commit_message: 'First save',
        created_by_name: 'Mei',
        created_at: '2026-09-12T00:00:00Z',
      },
    ]);
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: /History/ }));
    const row = await screen.findByTestId('request-version-1');

    fireEvent.click(within(row).getByRole('button', { name: /View/ }));

    await waitFor(() => expect(mockGetVersion).toHaveBeenCalledWith('req-1', 1));
    const lightbox = await screen.findByTestId('version-lightbox');
    expect(lightbox).toHaveTextContent('PT-202609-0001');
    expect(lightbox).toHaveTextContent('version 1');
    // The lightbox draws the payload the VERSION read answered (1), not the
    // live design's (7). Drawing the live one would tell the reader that v1
    // looked like today's draft.
    expect(lightbox.getAttribute('data-version')).toBe('1');
  });

  it('a version that will not load says so rather than opening a blank sheet', async () => {
    mockVersions.mockResolvedValue([
      {
        version: 1,
        commit_message: 'First save',
        created_by_name: 'Mei',
        created_at: '2026-09-12T00:00:00Z',
      },
    ]);
    mockGetVersion.mockRejectedValue(new Error('gone'));
    renderSection();
    fireEvent.click(await screen.findByRole('button', { name: /History/ }));
    const row = await screen.findByTestId('request-version-1');

    fireEvent.click(within(row).getByRole('button', { name: /View/ }));

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Could not open that version'),
    );
    expect(screen.queryByTestId('version-lightbox')).toBeNull();
  });
});
