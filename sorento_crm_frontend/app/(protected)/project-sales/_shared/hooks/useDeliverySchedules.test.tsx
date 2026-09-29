/**
 * S1-3 (R6) - confirming a schedule version names its "areas", not its "phases".
 *
 * The toast text is user-visible copy and easy to regress silently since nothing else on the
 * confirm path renders the word - pin it directly on the mutation's onSuccess branch.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const confirmDeliveryScheduleVersion = vi.fn();

vi.mock('../services/deliveryScheduleService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/deliveryScheduleService')>();
  return {
    ...actual,
    confirmDeliveryScheduleVersion: (...args: unknown[]) =>
      confirmDeliveryScheduleVersion(...args),
  };
});

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { useDeliveryScheduleVersionMutations } from './useDeliverySchedules';

const PROJECT_ID = 'proj-1';
const VERSION_ID = 'ver-1';

function Harness({
  onReady,
}: {
  onReady: (api: ReturnType<typeof useDeliveryScheduleVersionMutations>) => void;
}) {
  const api = useDeliveryScheduleVersionMutations(PROJECT_ID, VERSION_ID);
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

let client: QueryClient;

beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

async function confirmVersion(version: Record<string, unknown>) {
  confirmDeliveryScheduleVersion.mockResolvedValue(version);
  let api: ReturnType<typeof useDeliveryScheduleVersionMutations> | null = null;
  render(
    <QueryClientProvider client={client}>
      <Harness onReady={(value) => (api = value)} />
    </QueryClientProvider>,
  );
  await act(async () => {
    await api!.confirm.mutateAsync({} as never);
  });
}

describe('useDeliveryScheduleVersionMutations confirm', () => {
  it('toasts "Its areas are on the project" (R6, S1-3)', async () => {
    await confirmVersion({ id: VERSION_ID, amendment_preview_url: null });

    expect(toast.success).toHaveBeenCalledWith('Schedule confirmed. Its areas are on the project.');
    expect(toast.success).not.toHaveBeenCalledWith(expect.stringMatching(/phase/i));
  });

  it('still leads with the amendment link when the confirm goes stale (unchanged branch)', async () => {
    await confirmVersion({
      id: VERSION_ID,
      amendment_preview_url: '/project-sales/proj-1/sales-orders/pso-1/revisions',
    });

    expect(toast.success).toHaveBeenCalledWith(
      'Schedule confirmed - the linked sales order needs an amendment.',
      expect.objectContaining({ action: expect.any(Object) }),
    );
  });
});
