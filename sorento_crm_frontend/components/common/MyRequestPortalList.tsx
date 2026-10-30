'use client';

/**
 * A salesperson's own requests of one kind on its CRM list page (PORTAL-P4-REQUESTS L2, hand test
 * 3, owner a25895124 Q1 a): the PORTAL's own list body (`KindSubmissionList`: search, Filter,
 * Sort, card / list toggle, long-press preview), its rows and links through My Requests
 * (`MyRequestClientProvider`), as `MyRequestPortalForm` does for the form. Each of the 8 lists
 * renders it for a user limited to their own rows of its kind (`useRequestScope`); everyone else
 * keeps the staff DataGrid.
 *
 * Create needs the form's create grant (`MY_REQUEST_STAFF_PAGES[kind].create`). `onCreate`: the
 * page opens its own create (an opportunity's Log opportunity modal) instead of a `/new` page.
 */

import { KindSubmissionList } from '@/app/(auth)/portal/components/SubmissionList';
import { useHasPermission } from '@/hooks/usePermissions';
import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import type { PortalLandingKind } from '@/app/(auth)/portal/lib/portal-client';

export default function MyRequestPortalList({
  kind,
  onCreate,
}: {
  kind: PortalLandingKind;
  onCreate?: () => void;
}) {
  const canCreate = useHasPermission(
    MY_REQUEST_STAFF_PAGES[kind]?.create ?? 'request_scope.none',
  );
  return (
    <MyRequestClientProvider>
      <KindSubmissionList
        kind={kind}
        canCreate={canCreate}
        onCreate={onCreate}
      />
    </MyRequestClientProvider>
  );
}
