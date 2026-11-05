'use client';

import { useEffect, useRef } from 'react';
import { getSession } from 'next-auth/react';
import { recordQuotationView } from '../services/quotationSignService';
import { localStore } from '@/lib/storage';
import { randomId } from '@/lib/id';

export const VISITOR_KEY = 'sorento.quotationSign.visitor';

/** A random id for this browser, kept so the backend can apply its 30-minute rule. */
export function visitorId(): string {
  const fresh = randomId;
  try {
    const kept = localStore.getItem(VISITOR_KEY);
    if (kept && kept.length >= 8 && kept.length <= 128) return kept;
    const made = fresh();
    localStore.setItem(VISITOR_KEY, made);
    return made;
  } catch {
    // Private mode or blocked storage: a fresh id per load; the count may run one high.
    return fresh();
  }
}

/**
 * A browser signed in to the CRM as STAFF. A customer contact signed in to the portal also holds a
 * NextAuth session, and its home is `/portal/c/<slug>` (`home_path_for_user`,
 * phone_signin_service.py), so that one still counts. Every other home (`/`, the salesperson's
 * `/my-requests`) is staff.
 */
async function isStaffBrowser(): Promise<boolean> {
  try {
    const session = await getSession();
    if (!session?.user) return false;
    const home = (session.user as { homePath?: unknown }).homePath;
    return !(typeof home === 'string' && home.startsWith('/portal/'));
  } catch {
    return false;
  }
}

/**
 * Tells the backend the customer opened the quotation, once the page has loaded it. Sent once per
 * page load; a signed-in staff browser sends nothing (the salesperson checking their own link).
 */
export function useQuotationViewBeacon(token: string, loaded: boolean) {
  const sent = useRef(false);
  useEffect(() => {
    if (!loaded || !token || sent.current) return;
    sent.current = true;
    void (async () => {
      if (await isStaffBrowser()) return;
      await recordQuotationView(token, visitorId());
    })().catch(() => {});
  }, [token, loaded]);
}
