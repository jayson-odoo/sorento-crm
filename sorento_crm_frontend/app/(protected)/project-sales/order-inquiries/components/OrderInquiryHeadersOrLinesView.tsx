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
 * toggle away, URL-synced as `?display=lines`.
 *
 * NOT `?view=` (browser-pass DEFECT, fix round): `OrderInquiriesClient` already owns
 * `view` for its own List | Schedule toggle, and existing links/bookmarks carry
 * `view=schedule` - a second control keyed on the same param fights the first one's own
 * URL-sync effect, which reads `lines` as "not mine", defaults back to `list` and
 * deletes the key, kicking this switch back to Documents the instant the worklist
 * mounts. `display` is a name neither screen already uses.
 */
export function OrderInquiryHeadersOrLinesView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const view = viewFrom(searchParams.get('display'));

  // A CLEAN url on every toggle press, never a clone of the current one: Documents and
  // Lines each own a `state`/`agent`/`query` param with a DIFFERENT meaning (header
  // status vs. row state, agent name vs. agent id, OI/customer text vs. product text),
  // so carrying either screen's filters into the other reads as a filter that changed
  // meaning under the reader rather than one that reset. `OrderInquiryHeadersList`'s own
  // URL-sync effect already rebuilds its query string from scratch for the same reason;
  // this is the same rule at the one place both screens are chosen between.
  function setView(next: OrderInquiryTopView) {
    router.push(next === 'lines' ? `${pathname}?display=lines` : pathname);
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
