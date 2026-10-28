/**
 * PROJECT-REGISTER-V2 H3: a project picker clamps its trigger label. The PO intake upload
 * dialog's project picker passes `truncateTriggerLabel` so a 60-word title cannot grow the
 * trigger (representative of the picker sweep).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/pipeline',
  useSearchParams: () => ({ get: () => null }),
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const seen: Record<string, unknown>[] = [];
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: Record<string, unknown>) => {
    seen.push(props);
    return <input id={props.id as string} />;
  },
}));

import { POIntakeUploadDialog } from './POIntakeUploadDialog';

describe('H3 project picker trigger is clamped', () => {
  it('the PO intake project picker sets truncateTriggerLabel', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <POIntakeUploadDialog projectId={undefined} purchaseOrderId={null} purchaseOrderNumber={null} onDone={() => {}} />
      </QueryClientProvider>,
    );
    const picker = seen.find((p) => p.id === 'po-upload-project');
    expect(picker, 'project picker was not rendered').toBeTruthy();
    expect(picker!.truncateTriggerLabel).toBe(true);
  });
});
