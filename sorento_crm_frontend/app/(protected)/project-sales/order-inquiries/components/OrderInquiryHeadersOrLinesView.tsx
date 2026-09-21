'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { FileStack, List } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/PageHeader';
import { OrderInquiriesClient } from './OrderInquiriesClient';
import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

type OrderInquiryTopView = 'documents' | 'lines';

function viewFrom(value: string | null): OrderInquiryTopView {
  return value === 'lines' ? 'lines' : 'documents';
}

/**
 * `PLAN-oi-header-list-detail.md`, S4/AC-HL-01. The page's own top-level switch: one row
 * per order inquiry DOCUMENT (`OrderInquiryHeadersList`, the default screen this lane
 * adds) or today's per-LINE worklist (`OrderInquiriesClient`, untouched behaviour) - one
 * toggle away, URL-synced as `?view=lines`.
 */
export function OrderInquiryHeadersOrLinesView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const view = viewFrom(searchParams.get('view'));

  function setView(next: OrderInquiryTopView) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === 'lines') params.set('view', 'lines');
    else params.delete('view');
    const qs = params.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  const toggle = (
    <div
      className="inline-flex rounded-md border border-input"
      role="group"
      aria-label="Order inquiries view"
    >
      <Button
        type="button"
        size="sm"
        variant={view === 'documents' ? 'primary' : 'ghost'}
        className="rounded-e-none"
        aria-pressed={view === 'documents'}
        onClick={() => setView('documents')}
      >
        <FileStack className="size-4" aria-hidden />
        Documents
      </Button>
      <Button
        type="button"
        size="sm"
        variant={view === 'lines' ? 'primary' : 'ghost'}
        className="rounded-s-none border-s border-input"
        aria-pressed={view === 'lines'}
        onClick={() => setView('lines')}
      >
        <List className="size-4" aria-hidden />
        Lines
      </Button>
    </div>
  );

  if (view === 'lines') {
    // `OrderInquiriesClient` owns its own `PageHeader` (title + its own List | Schedule
    // toggle) - this one's toggle rides in the SAME header, beside it, rather than a
    // second `PageHeader` stacked above.
    return <OrderInquiriesClient extraHeaderActions={toggle} />;
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Order inquiries" actions={toggle} />
      <OrderInquiryHeadersList />
    </div>
  );
}

export default OrderInquiryHeadersOrLinesView;
