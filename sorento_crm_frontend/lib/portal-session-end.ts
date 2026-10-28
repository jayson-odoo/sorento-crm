import { clearPortalToken, portalLogout } from '@/app/(auth)/portal/lib/portal-client';
import { clearPortalSlug } from '@/app/(auth)/portal/lib/portal-paths';

/**
 * End the portal session on this device when the user signs out of the CRM (a salesperson uses
 * both): best-effort server logout, then the stored token and slug are always cleared. A failure
 * never blocks the CRM sign-out.
 */
export async function endPortalSession(): Promise<void> {
  try {
    await portalLogout();
  } catch {
    // best effort
  }
  clearPortalToken();
  clearPortalSlug();
}
