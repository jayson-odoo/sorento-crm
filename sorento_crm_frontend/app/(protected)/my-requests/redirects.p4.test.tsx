/**
 * PORTAL-P4-REQUESTS S-FE0 (P4-20, deep links): the four form kinds under /my-requests send the visitor to the
 * STAFF page for that form. Either `redirect()` or `router.replace()` counts; what is asserted is where it lands.
 *   /my-requests?type=<kind>            -> staff list
 *   /my-requests/<kind>/new             -> staff /new
 *   /my-requests/<kind>/<id>            -> staff detail
 */
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
    salesperson: { portalKinds: ['stock_inquiry', 'complaint', 'purchase_request', 'sponsorship_form'], portalSlug: 'S1' },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="embedded-landing" /> }));
vi.mock('@/app/(auth)/portal/components/SubmissionForm', () => ({ SubmissionForm: () => <div data-testid="embedded-form" /> }));

import MyRequestsPage from './page';
import NewPage from './[type]/new/page';
import DetailPage from './[type]/[id]/page';

const STAFF: Record<string, string> = {
  stock_inquiry: '/procurement-management/stock-inquiries',
  complaint: '/complaint-management/complaints',
  purchase_request: '/procurement-management/purchase-requests',
  sponsorship_form: '/procurement-management/sponsorship-forms',
};

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
});

describe('deep links into the staff pages', () => {
  it.each(Object.keys(STAFF))('/my-requests?type=%s lands on the staff list', async (kind) => {
    query.type = kind;
    await mount(<MyRequestsPage {...({ searchParams: Promise.resolve({ type: kind }) } as object)} />);
    await waitFor(() => expect(landed).toContain(STAFF[kind]));
  });

  it.each(Object.keys(STAFF))('/my-requests/%s/new lands on the staff /new', async (kind) => {
    await mount(<NewPage params={Promise.resolve({ type: kind })} />);
    await waitFor(() => expect(landed).toContain(`${STAFF[kind]}/new`));
  });

  it.each(Object.keys(STAFF))('/my-requests/%s/<id> lands on the staff detail', async (kind) => {
    await mount(<DetailPage params={Promise.resolve({ type: kind, id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain(`${STAFF[kind]}/abc-123`));
  });

  it('never renders the embedded portal form for these kinds', async () => {
    const { queryByTestId } = render(
      <Suspense fallback={null}>
        <NewPage params={Promise.resolve({ type: 'stock_inquiry' })} />
      </Suspense>,
    );
    await act(async () => {});
    expect(queryByTestId('embedded-form')).toBeNull();
  });
});
