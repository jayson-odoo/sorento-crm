'use client';

import { useEffect, useRef } from 'react';
import { getSession } from 'next-auth/react';
import { recordQuotationView } from '../services/quotationSignService';

export const VISITOR_KEY = 'sorento.quotationSign.visitor';

/** A random id for this browser, kept so the backend can apply its 30-minute rule. */
export function visitorId(): string {
  const fresh = () =>
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  try {
    const kept = window.localStorage.getItem(VISITOR_KEY);
    if (kept && kept.length >= 8 && kept.length <= 128) return kept;
    const made = fresh();
    window.localStorage.setItem(VISITOR_KEY, made);
    return made;
  } catch {
    // Private mode or blocked storage: a fresh id per load; the count may run one high.
    return fresh();
  }
}

/**
 * A browser signed in to the CRM as STAFF. A portal contact also holds a NextAuth session (their
 * home is under /my-requests) and is a customer, so they still count.
 */
async function isStaffBrowser(): Promise<boolean> {
  try {
    const session = await getSession();
    if (!session?.user) return false;
    const home = (session.user as { homePath?: unknown }).homePath;
    return !(typeof home === 'string' && home.startsWith('/my-requests'));
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
