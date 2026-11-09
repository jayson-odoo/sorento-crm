import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * SORENTO-TOWN Phase 1: the town screen shell (plan "Phase 1 screen").
 *
 * Assumed: `import { TownPage } from './TownPage'` (the client component `page.tsx` renders), which
 * reads `useTownSnapshot()` from `@/hooks/useTownSnapshot` (`{ snapshot, error, isLoading }`) and
 * mounts `./TownScene` only through `next/dynamic`. The scene is stubbed here with a test id.
 */
const snapshotState: { snapshot: unknown } = { snapshot: undefined };
vi.mock('@/hooks/useTownSnapshot', () => ({
  useTownSnapshot: () => ({ snapshot: snapshotState.snapshot, error: null, isLoading: false }),
}));
vi.mock('next/dynamic', () => ({
  default: () => {
    const Scene = () => <div data-testid="town-scene" />;
    return Scene;
  },
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/town',
  useSearchParams: () => new URLSearchParams(),
}));

import { TownPage } from './TownPage';

const FULL = {
  schema: 1,
  company_id: '00000000-0000-0000-0000-000000000001',
  day: '2026-11-03',
  as_of: '2026-11-03T15:42:00+08:00',
  data_as_of: null,
  phase: 'day',
  today: { amount: '1000.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 2 },
  compare: { label: 'Tue 27 Oct', last_week_amount: '900.00', last_week_invoice_count: 2 },
  shops: [],
  warehouses: [],
  reorder: { below_count: 4, set_count: 9 },
  deliveries: { to_deliver: 2 },
  approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TownPage />
    </QueryClientProvider>,
  );
}

function stubWebGL(available: boolean) {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    (() => (available ? ({} as unknown) : null)) as never,
  );
}

function stubMotion(reduce: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: reduce && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      onchange: null,
      dispatchEvent: () => false,
    }),
  });
}

beforeEach(() => {
  snapshotState.snapshot = FULL;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TownPage', () => {
  it('mounts the 3D scene and the cards when WebGL works and motion is allowed', () => {
    stubWebGL(true);
    stubMotion(false);
    renderPage();
    expect(screen.getByTestId('town-scene')).toBeTruthy();
    expect(screen.getByText('How much did we sell today?')).toBeTruthy();
  });

  it('shows the cards and not the scene when WebGL is unavailable', () => {
    stubWebGL(false);
    stubMotion(false);
    renderPage();
    expect(screen.queryByTestId('town-scene')).toBeNull();
    expect(screen.getByText('How much did we sell today?')).toBeTruthy();
    expect(screen.getByText('What needs a decision?')).toBeTruthy();
  });

  it('shows the cards and not the scene when the user prefers reduced motion', () => {
    stubWebGL(true);
    stubMotion(true);
    renderPage();
    expect(screen.queryByTestId('town-scene')).toBeNull();
    expect(screen.getByText('What must go out?')).toBeTruthy();
  });

  it('has the page title Town and one Wallboard button', () => {
    stubWebGL(false);
    stubMotion(false);
    renderPage();
    expect(screen.getByRole('heading', { name: 'Town' })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /wallboard/i })).toHaveLength(1);
  });

  it('shows an empty state with no button of its own while the first snapshot is pending', () => {
    stubWebGL(false);
    stubMotion(false);
    snapshotState.snapshot = { pending: true };
    renderPage();
    expect(screen.queryByText('How much did we sell today?')).toBeNull();
    expect(screen.queryByTestId('town-scene')).toBeNull();
    // the header's Wallboard is the only CTA; the empty state adds none
    expect(screen.getAllByRole('button').length).toBeLessThanOrEqual(1);
  });
});

describe('the 3D code stays off every other page (AC-11)', () => {
  const dir = path.resolve(__dirname, '..');
  const read = (rel: string) => fs.readFileSync(path.join(dir, rel), 'utf8');

  it('page.tsx exists and renders the client TownPage', () => {
    expect(fs.existsSync(path.join(dir, 'page.tsx'))).toBe(true);
    expect(read('page.tsx')).toContain('TownPage');
  });

  it('loads the scene through next/dynamic with ssr: false', () => {
    const source = read('page.tsx') + '\n' + read('components/TownPage.tsx');
    expect(source).toContain('dynamic(');
    expect(source).toMatch(/ssr:\s*false/);
    expect(source).toContain('TownScene');
  });

  it('never imports three or the scene statically from the page or the shell', () => {
    for (const file of ['page.tsx', 'components/TownPage.tsx']) {
      const source = read(file);
      expect(source, file).not.toMatch(/^\s*import[^;]*from\s+['"]three['"]/m);
      expect(source, file).not.toMatch(/^\s*import[^;]*from\s+['"]three\//m);
      expect(source, file).not.toMatch(/^\s*import\s+[^;]*from\s+['"]\.\/TownScene['"]/m);
      expect(source, file).not.toMatch(/^\s*import\s+[^;]*from\s+['"]\.\/components\/TownScene['"]/m);
    }
  });
});
