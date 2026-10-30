/**
 * PORTAL-P4-REQUESTS S4 + S6 (deep links): Sample Request and Sales Opportunity under /my-requests send the
 * visitor to the STAFF page. Either `redirect()` or `router.replace()` counts; what is asserted is where it lands.
 *   /my-requests?type=<kind>              -> staff list
 *   /my-requests/sample_request/new       -> staff /new
 *   /my-requests/sample_request/<id>      -> staff detail
 *   /my-requests/sales_opportunity/new    -> the staff list (the create modal lives there)
 *   /my-requests/sales_opportunity/<id>   -> staff detail
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
    salesperson: { portalKinds: ['sample_request', 'sales_opportunity'], portalSlug: 'S1' },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock('@/app/(auth)/portal/components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="embedded-landing" /> }));
vi.mock('@/app/(auth)/portal/components/SampleRequestForm', () => ({ default: () => <div data-testid="embedded-form" /> }));
vi.mock('@/app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalForm', () => ({ default: () => <div data-testid="embedded-form" /> }));
vi.mock('@/app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalDetail', () => ({ default: () => <div data-testid="embedded-form" /> }));

import MyRequestsPage from './page';
import SampleNew from './sample_request/new/page';
import SampleDetail from './sample_request/[id]/page';
import OppNew from './sales_opportunity/new/page';
import OppDetail from './sales_opportunity/[id]/page';

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

describe('Sample Request deep links', () => {
  it('/my-requests?type=sample_request lands on the staff list', async () => {
    query.type = 'sample_request';
    await mount(<MyRequestsPage {...({ searchParams: Promise.resolve({ type: 'sample_request' }) } as object)} />);
    await waitFor(() => expect(landed).toContain('/project-sales/sample-requests'));
  });
  it('/my-requests/sample_request/new lands on the staff /new', async () => {
    await mount(<SampleNew />);
    await waitFor(() => expect(landed).toContain('/project-sales/sample-requests/new'));
  });
  it('/my-requests/sample_request/<id> lands on the staff detail', async () => {
    await mount(<SampleDetail params={Promise.resolve({ id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain('/project-sales/sample-requests/abc-123'));
  });
});

describe('Sales Opportunity deep links', () => {
  it('/my-requests?type=sales_opportunity lands on the staff list', async () => {
    query.type = 'sales_opportunity';
    await mount(<MyRequestsPage {...({ searchParams: Promise.resolve({ type: 'sales_opportunity' }) } as object)} />);
    await waitFor(() => expect(landed).toContain('/sales/opportunities'));
  });
  it('/my-requests/sales_opportunity/new lands on the staff list', async () => {
    await mount(<OppNew />);
    await waitFor(() => expect(landed.some((p) => p === '/sales/opportunities' || p.startsWith('/sales/opportunities?'))).toBe(true));
  });
  it('/my-requests/sales_opportunity/<id> lands on the staff detail', async () => {
    await mount(<OppDetail params={Promise.resolve({ id: 'abc-123' })} />);
    await waitFor(() => expect(landed).toContain('/sales/opportunities/abc-123'));
  });
  it('never renders the embedded portal form for these kinds', async () => {
    const { queryByTestId } = render(
      <Suspense fallback={null}>
        <SampleNew />
        <OppNew />
      </Suspense>,
    );
    await act(async () => {});
    expect(queryByTestId('embedded-form')).toBeNull();
  });
});
