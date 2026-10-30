'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';
import { MY_REQUEST_STAFF_PAGES, myRequestStaffPath } from '@/lib/my-requests-staff-pages';

const FALLBACK = MY_REQUEST_STAFF_PAGES.stock_inquiry.path;

/**
 * The MY REQUESTS landing is a redirect: the starred form's staff list (the star lives in this
 * browser, keyed by the contact), else Stock Inquiry. `?type=<kind>` goes straight to that list.
 */
export default function MyRequestsPage() {
  const router = useRouter();
  const type = useSearchParams()?.get('type');
  const { salesperson, isLoading } = useAccountProfileForHeader();
  const contactId = salesperson?.contactId ?? null;
  const typed = myRequestStaffPath(type);

  useEffect(() => {
    if (typed) {
      router.replace(typed);
      return;
    }
    if (isLoading) return;
    let star: string | null = null;
    if (contactId && typeof window !== 'undefined') {
      star = window.localStorage.getItem(`sorento.portalDefaultTab.${contactId}`);
    }
    router.replace(myRequestStaffPath(star) ?? FALLBACK);
  }, [typed, isLoading, contactId, router]);

  return null;
}
