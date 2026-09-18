/**
 * Shared supplier select service for dropdowns outside SCM's own feature tree (review
 * round 2, item 6) - the server-searched, paged lookup (`SearchableSelect`'s
 * `fetchOptions(query, pageIndex)` contract) SCM's own pickers already use, re-exported
 * under a select-service name so a caller elsewhere in the app does not reach into
 * `app/(protected)/scm/services/...` for it. Same pattern as `userSelectService.ts` for
 * users; SCM's own callers (`PlanContainerDialog`, the upload dialogs) keep importing
 * `getFulfilmentSuppliers` directly - they are already inside that feature tree.
 */
export { getFulfilmentSuppliers as getSuppliersSelect } from '@/app/(protected)/scm/services/fulfilmentService';
