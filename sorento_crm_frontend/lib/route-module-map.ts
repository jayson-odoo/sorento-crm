/**
 * Map URL prefixes (protected app routes) to installable module keys.
 * Longer prefixes should appear first so more specific routes win.
 */
export const ROUTE_MODULE_PREFIXES: { prefix: string; moduleKey: string }[] = [
  { prefix: '/order-management', moduleKey: 'order' },
  { prefix: '/master-data-management', moduleKey: 'product' },
  { prefix: '/complaint-management', moduleKey: 'complaints' },
  { prefix: '/sla-management', moduleKey: 'sla' },
  { prefix: '/procurement-management', moduleKey: 'procurement' },
  { prefix: '/inventory-management', moduleKey: 'inventory' },
  { prefix: '/marketing-management', moduleKey: 'marketing' },
  { prefix: '/forms-management', moduleKey: 'forms' },
  { prefix: '/workflow-forms-management', moduleKey: 'workflow_forms' },
  { prefix: '/resource-management', moduleKey: 'resources' },
  { prefix: '/integration-management', moduleKey: 'base' },
  { prefix: '/system-management', moduleKey: 'base' },
  { prefix: '/user-management', moduleKey: 'base' },
];

export function moduleKeyForPath(pathname: string): string | null {
  const path = pathname.split('?')[0] || '/';
  for (const { prefix, moduleKey } of ROUTE_MODULE_PREFIXES) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      return moduleKey;
    }
  }
  return null;
}
