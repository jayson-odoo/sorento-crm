/**
 * PORTAL-P4-REQUESTS S8 (owner card v1 Q5 c): no embedded portal view is left inside the CRM.
 * All 8 MY REQUESTS kinds open on their STAFF pages; every /my-requests route redirects (to a staff
 * page, or the landing = the Stock Inquiry staff list); no portal component is importable from here.
 */
import fs from 'node:fs';
import path from 'node:path';
import React, { Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';

const landed: string[] = [];
const query = { type: '' };
class Redirected extends Error {}
vi.mock('next/navigation', () => ({
  redirect: (to: string) => {
    landed.push(to);
    throw new Redirected(to);
  },
  permanentRedirect: (to: string) => {
    landed.push(to);
    throw new Redirected(to);
  },
  notFound: () => {
    throw new Error('notFound');
  },
  useRouter: () => ({
    replace: (to: string) => landed.push(to),
    push: (to: string) => landed.push(to),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(query.type ? `type=${query.type}` : ''),
  usePathname: () => '/my-requests',
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: { portalKinds: [], portalSlug: 'S1', contactId: 'c-1' },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="embedded" /> }));
vi.mock('@/app/(auth)/portal/components/SubmissionForm', () => ({
  SubmissionForm: () => <div data-testid="embedded" />,
}));
vi.mock('@/app/(auth)/portal/components/PortalVerifyCard', () => ({
  PortalVerifyCard: () => <div data-testid="embedded" />,
}));

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import MyRequestsPage from './page';
import TypeNew from './[type]/new/page';
import TypeDetail from './[type]/[id]/page';
import VerifyPage from './verify/page';

const STAFF: Record<string, string> = {
  stock_inquiry: '/procurement-management/stock-inquiries',
  complaint: '/complaint-management/complaints',
  purchase_request: '/procurement-management/purchase-requests',
  sponsorship_form: '/procurement-management/sponsorship-forms',
  sample_request: '/project-sales/sample-requests',
  new_product_application: '/procurement-management/new-product-applications',
  price_tag_request: '/dealer-kit/price-tag-requests',
  sales_opportunity: '/sales/opportunities',
};
const KINDS = Object.keys(STAFF);

async function mount(node: React.ReactElement) {
  try {
    await act(async () => {
      render(<Suspense fallback={null}>{node}</Suspense>);
    });
  } catch (e) {
    if (!(e instanceof Redirected)) throw e;
  }
}

beforeEach(() => {
  landed.length = 0;
  query.type = '';
  window.localStorage.clear();
});

describe('S8: the staff-page map covers all 8 kinds', () => {
  it('MY_REQUEST_STAFF_PAGES holds exactly the 8 kinds with their staff list paths', () => {
    expect(Object.fromEntries(Object.entries(MY_REQUEST_STAFF_PAGES).map(([k, v]) => [k, v.path]))).toEqual(STAFF);
  });
});

describe.each(KINDS)('S8: /my-requests deep links for %s', (kind) => {
  it('?type=<kind> lands on the staff list, nothing embedded', async () => {
    query.type = kind;
    const view = await (async () => {
      await mount(<MyRequestsPage />);
      return document.body;
    })();
    await waitFor(() => expect(landed).toContain(STAFF[kind]));
    expect(view.querySelector('[data-testid="embedded"]')).toBeNull();
  });
  it('/<kind>/new lands on the staff new page', async () => {
    await mount(<TypeNew params={Promise.resolve({ type: kind })} />);
    await waitFor(() => expect(landed).toContain(`${STAFF[kind]}/new`));
    expect(document.querySelector('[data-testid="embedded"]')).toBeNull();
  });
  it('/<kind>/<id> lands on the staff detail page', async () => {
    await mount(<TypeDetail params={Promise.resolve({ type: kind, id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain(`${STAFF[kind]}/abc-123`));
    expect(document.querySelector('[data-testid="embedded"]')).toBeNull();
  });
});

describe('S8: landing and verify', () => {
  it('/my-requests with a starred favourite goes to that kind\'s staff list', async () => {
    window.localStorage.setItem('sorento.portalDefaultTab.c-1', 'complaint');
    await mount(<MyRequestsPage />);
    await waitFor(() => expect(landed).toContain(STAFF.complaint));
    expect(document.querySelector('[data-testid="embedded"]')).toBeNull();
  });
  it('/my-requests with a star that is not one of the 8 kinds falls back to Stock Inquiry', async () => {
    window.localStorage.setItem('sorento.portalDefaultTab.c-1', 'project_registration');
    await mount(<MyRequestsPage />);
    await waitFor(() => expect(landed).toContain(STAFF.stock_inquiry));
  });
  it('/my-requests with no star goes to the Stock Inquiry staff list and renders no PortalLanding', async () => {
    await mount(<MyRequestsPage />);
    await waitFor(() => expect(landed).toContain(STAFF.stock_inquiry));
    expect(document.querySelector('[data-testid="embedded"]')).toBeNull();
  });
  it('/my-requests/verify redirects away from /my-requests and renders no portal verify card', async () => {
    await mount(<VerifyPage />);
    await waitFor(() => expect(landed.length).toBeGreaterThan(0));
    expect(landed.every((p) => !p.startsWith('/my-requests'))).toBe(true);
    expect(document.querySelector('[data-testid="embedded"]')).toBeNull();
  });
});

describe('S8: no embedded portal component is importable from app/(protected)/my-requests', () => {
  const root = path.resolve(__dirname);
  const walk = (dir: string): string[] =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
      const p = path.join(dir, e.name);
      return e.isDirectory() ? walk(p) : [p];
    });
  const sources = walk(root).filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));

  it('no non-test source imports from (auth)/portal', () => {
    const offenders = sources.filter((f) => /from\s+['"][^'"]*\(auth\)\/portal[^'"]*['"]/.test(fs.readFileSync(f, 'utf8')));
    expect(offenders.map((f) => path.relative(root, f))).toEqual([]);
  });
  it('MySlug and the portal-token machinery are gone from the folder', () => {
    expect(sources.map((f) => path.basename(f))).not.toContain('MySlug.tsx');
  });
});
