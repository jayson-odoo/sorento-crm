import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ExtendDueButton from './ExtendDueButton';

// The dialog is rendered lazily on open; stub the service module it pulls in so the
// import graph resolves without network in jsdom.
vi.mock('../services/conversationSLATrackingService', () => ({
  getExtendPreview: vi.fn(),
  extendSLATracking: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

function renderButton(props: Partial<React.ComponentProps<typeof ExtendDueButton>>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExtendDueButton
        trackingId="t1"
        currentDueAt="2026-07-01T09:00:00"
        isResolved={false}
        isAssignee
        {...props}
      />
    </QueryClientProvider>,
  );
}

const btn = () => screen.queryByRole('button', { name: /extend/i });

describe('ExtendDueButton gating', () => {
  // UAC-1 (FE): all gates pass -> shown.
  it('renders when unresolved, assignee, no takeover, has resolution due', () => {
    renderButton({});
    expect(btn()).toBeInTheDocument();
  });

  // UAC-3 (FE): resolved -> hidden.
  it('hidden when isResolved', () => {
    renderButton({ isResolved: true });
    expect(btn()).not.toBeInTheDocument();
  });

  // UAC-2 (FE): not assignee -> hidden.
  it('hidden when not assignee', () => {
    renderButton({ isAssignee: false });
    expect(btn()).not.toBeInTheDocument();
  });

  // UAC-5 (FE): pending takeover -> hidden/locked.
  it('hidden when takeover is pending', () => {
    renderButton({ takeoverPending: true });
    expect(btn()).not.toBeInTheDocument();
  });

  // UAC-4 (FE): no resolution deadline (null) -> hidden.
  it('hidden when currentDueAt is null', () => {
    renderButton({ currentDueAt: null });
    expect(btn()).not.toBeInTheDocument();
  });

  // UAC-4 (FE): unknown due + 'require' policy -> hidden.
  it("hidden when currentDueAt is undefined under 'require' policy", () => {
    renderButton({ currentDueAt: undefined, unknownDuePolicy: 'require' });
    expect(btn()).not.toBeInTheDocument();
  });

  // UAC-1 (FE): unknown due + 'allow-unknown' policy (My Pending widget) -> shown.
  it("shown when currentDueAt is undefined under 'allow-unknown' policy", () => {
    renderButton({ currentDueAt: undefined, unknownDuePolicy: 'allow-unknown' });
    expect(btn()).toBeInTheDocument();
  });
});
