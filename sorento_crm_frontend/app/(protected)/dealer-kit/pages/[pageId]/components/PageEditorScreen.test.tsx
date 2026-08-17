/**
 * The editor header's action contract.
 *
 * This row carried SIX buttons at equal weight - export, view live, design a
 * room, history, save, publish - and the two that actually change the catalogue
 * were the hardest to find among them. These assertions pin the shape it was
 * cut down to, because "add one more button to the header" is the easiest
 * change in the world to make and the row grows back one commit at a time.
 *
 * The rule: SAVE and PUBLISH in the header, exactly one of them primary,
 * everything else behind the gear (DetailActionsMenu) - which is the pattern
 * complaints, purchase requests and stock inquiries already use.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Radix renders its menu into a portal only once a real pointer opens it, which
// jsdom does not do. Both primitives are stubbed so the menu's CONTENTS render
// inline inside a known container - which is exactly what these assertions are
// about: whether an action sits in the header or behind the gear.
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({
    children,
    ariaLabel,
  }: {
    children: React.ReactNode;
    ariaLabel?: string;
  }) => (
    <div data-testid="gear-menu" aria-label={ariaLabel}>
      {children}
    </div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: (props: React.ComponentProps<'div'> & { asChild?: boolean }) => {
    // `asChild` is a Radix concern and must not reach the DOM, so it is peeled
    // off rather than spread.
    const { children, asChild, ...rest } = props;
    void asChild;
    return (
      <div role="menuitem" {...rest}>
        {children}
      </div>
    );
  },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/pages/pg-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ pageId: 'pg-1' }),
}));

vi.mock('../../../services/dealerKitService', () => ({
  getPage: vi.fn(),
  saveVersion: vi.fn(),
  moveLabel: vi.fn(),
  requestExport: vi.fn(),
}));

// The editor body is a large drag-and-drop surface with its own tests. What is
// under review here is the header, so the body is stubbed out.
vi.mock('../../../components/PageEditor', () => ({
  PageEditor: () => <div data-testid="stub-editor" />,
}));
vi.mock('./PagePromotionControl', () => ({
  PagePromotionControl: () => <div data-testid="stub-promotion" />,
}));
vi.mock('./VersionHistory', () => ({
  VersionHistory: () => <div data-testid="stub-history" />,
}));

import { getPage } from '../../../services/dealerKitService';
import { PageEditorScreen } from './PageEditorScreen';

const mockGetPage = vi.mocked(getPage);

/** A published page: the state where every optional action is available. */
function publishedPage() {
  return {
    id: 'pg-1',
    name: 'Sorento Catalogue 2026',
    slug: 'sorento-2026',
    publicPath: '/c/SRT/sorento-2026',
    promotionId: null,
    paper: { profile: 'A4', orientation: 'portrait', cover: false },
    doc: { sections: [] },
    versions: [{ id: 'v-1', version: 1, createdAt: '', createdBy: null, labels: ['published'] }],
    labels: { published: ['v-1'] },
  };
}

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PageEditorScreen pageId="pg-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetPage.mockResolvedValue(publishedPage() as never);
});

describe('PageEditorScreen header', () => {
  it('puts only Save and Publish in the header', async () => {
    renderScreen();
    const publish = await screen.findByRole('button', { name: /publish/i });

    // Every header BUTTON that is not the gear trigger. Anything else that
    // wants to live here has to displace one of these two.
    const gear = screen.getByTestId('gear-menu');
    const headerButtons = Array.from(
      publish.parentElement!.querySelectorAll('button'),
    ).filter((element) => !gear.contains(element));

    expect(headerButtons.map((element) => element.textContent?.trim())).toEqual([
      'Save',
      'Publish',
    ]);
  });

  it('offers exactly one primary action', async () => {
    // Publish is the consequential act - it is what readers see - so it is the
    // one that carries the primary styling. Save is deliberately secondary:
    // saving is a step towards publishing, not the goal.
    renderScreen();
    const publish = await screen.findByRole('button', { name: /publish/i });
    const save = screen.getByRole('button', { name: /^save$/i });

    expect(publish.className).not.toMatch(/border-input|bg-background/);
    expect(save.className).toMatch(/border|outline/);
  });

  it('keeps the secondary actions reachable under the gear', async () => {
    renderScreen();
    await screen.findByRole('button', { name: /publish/i });

    const gear = within(screen.getByTestId('gear-menu'));

    expect(gear.getByRole('menuitem', { name: /version history/i })).toBeInTheDocument();
    expect(gear.getByRole('menuitem', { name: /design a room/i })).toBeInTheDocument();
    expect(gear.getByRole('menuitem', { name: /export pdf/i })).toBeInTheDocument();
    expect(gear.getByRole('menuitem', { name: /view live/i })).toBeInTheDocument();
  });

  it('hides the live-only actions on a page nobody has published', async () => {
    // Exporting a draft produces a file that disagrees with the catalogue, and
    // a link to an unpublished page 404s. Hidden rather than disabled: an item
    // that can never be used on a draft is noise on a draft.
    mockGetPage.mockResolvedValue({
      ...publishedPage(),
      publicPath: null,
      versions: [{ id: 'v-1', version: 1, createdAt: '', createdBy: null, labels: [] }],
      labels: {},
    } as never);

    renderScreen();
    await screen.findByRole('button', { name: /publish/i });

    const gear = within(screen.getByTestId('gear-menu'));

    expect(gear.getByRole('menuitem', { name: /version history/i })).toBeInTheDocument();
    expect(gear.queryByRole('menuitem', { name: /export pdf/i })).toBeNull();
    expect(gear.queryByRole('menuitem', { name: /view live/i })).toBeNull();
  });
});
