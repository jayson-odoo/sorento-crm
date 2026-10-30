'use client';

import { useEffect } from 'react';
import { getSession } from 'next-auth/react';
import { crmPathForPortalPath } from '../lib/portal-paths';

/**
 * A signed-in salesperson who opens a portal link is sent to its CRM twin under /my-requests
 * (PORTAL-P3-ROLE-MENU). Anyone else, and any page without a twin (verify, legacy), stays put.
 */
export default function SalespersonCrmRedirect() {
  useEffect(() => {
    const { pathname, search } = window.location;
    const twin = crmPathForPortalPath(`${pathname}${search}`);
    if (!twin) return;
    let cancelled = false;
    void getSession()
      .then((session) => {
        const home = (session?.user as { homePath?: unknown } | undefined)?.homePath;
        if (!cancelled && typeof home === 'string' && home.startsWith('/my-requests')) {
          window.location.replace(twin);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
