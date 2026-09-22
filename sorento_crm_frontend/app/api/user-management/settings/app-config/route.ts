import { NextRequest } from 'next/server';
import { proxyToFastAPI } from '@/lib/api-proxy';

/**
 * The narrow, non-sensitive settings projection (`AppConfigResponse`,
 * `app/api/v1/user_management/settings.py`) - gated on plain authentication, not
 * `user_management.settings.view`, so a screen a non-admin role renders (currency
 * format, the default approver email, the reserve dialog's default pool) can read it.
 *
 * `useCurrencyFormat.ts` / `use-excel-accept.ts` / `PurchaseRequestDetail.tsx` /
 * `PriceTagRequestDetail.tsx` already call `/api/user-management/settings/app-config`
 * - this file was the missing proxy route (measured: no `route.ts` existed under this
 * path, so every one of those calls 404s at runtime today; a pre-existing gap this
 * lane's own `useReserveRowOptions.ts` read now depends on too).
 */
export async function GET(req: NextRequest) {
  return proxyToFastAPI(req, '/api/v1/user-management/settings/app-config');
}
