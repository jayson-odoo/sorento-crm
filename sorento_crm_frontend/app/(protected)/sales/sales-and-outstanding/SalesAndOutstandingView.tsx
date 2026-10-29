'use client';

import { ReportPage } from '@/components/reports/ReportPage';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useHasPermission, usePermissions } from '@/hooks/usePermissions';
import { useUrlTab } from '@/hooks/useUrlTab';

const REPORTS_VIEW = 'sales.reports.view';
const ORDERS_VIEW = 'order_management.orders.view';
// Unpaid invoices are receivables: finance data, behind the billing documents slug (security review B1).
const FINANCE_VIEW = 'finance.billing_documents.view';

/** One tab per basis, each its own report definition (the ones the chatbot's report ask runs). */
export const SALES_AND_OUTSTANDING_TABS = [
  { value: 'invoiced', label: 'Invoiced', reportKey: 'sales_invoiced_ask', permission: REPORTS_VIEW },
  { value: 'delivered', label: 'Delivered', reportKey: 'sales_order_lines_ask_delivered', permission: ORDERS_VIEW },
  { value: 'ordered', label: 'Ordered', reportKey: 'sales_order_lines_ask_ordered', permission: ORDERS_VIEW },
  {
    value: 'undelivered',
    label: 'Undelivered orders',
    reportKey: 'sales_order_lines_ask_outstanding',
    permission: ORDERS_VIEW,
  },
  { value: 'pending-delivery', label: 'Pending delivery', reportKey: 'delivery_order_lines_pending', permission: ORDERS_VIEW },
  { value: 'unpaid', label: 'Unpaid invoices', reportKey: 'unpaid_documents', permission: FINANCE_VIEW },
] as const;

type TabValue = (typeof SALES_AND_OUTSTANDING_TABS)[number]['value'];

const CRUMBS = [{ title: 'Sales' }, { title: 'Sales & outstanding' }];

export function SalesAndOutstandingView() {
  const { isLoading } = usePermissions();
  const canReports = useHasPermission(REPORTS_VIEW);
  const canOrders = useHasPermission(ORDERS_VIEW);
  const canFinance = useHasPermission(FINANCE_VIEW);
  const allowed: Record<string, boolean> = {
    [REPORTS_VIEW]: canReports,
    [ORDERS_VIEW]: canOrders,
    [FINANCE_VIEW]: canFinance,
  };
  const visible = SALES_AND_OUTSTANDING_TABS.filter((t) => allowed[t.permission]);
  const [active, setTab] = useUrlTab<TabValue>({
    tabs: visible.map((t) => t.value),
    defaultTab: visible[0]?.value ?? 'invoiced',
    basePath: '/sales/sales-and-outstanding',
  });
  const current = visible.find((t) => t.value === active) ?? visible[0];
  if (!current) {
    // No tab permitted: an explicit empty state (heading and hint, no button), once the permissions have loaded.
    if (isLoading) return null;
    return (
      <Container>
        <PageHeader title="Sales & outstanding" crumbs={CRUMBS} />
        <Card>
          <CardContent className="space-y-1 py-10 text-center">
            <h2 className="text-base font-medium">No reports available</h2>
            <p className="text-sm text-muted-foreground">Your account has no sales or outstanding reports.</p>
          </CardContent>
        </Card>
      </Container>
    );
  }

  return (
    <ReportPage
      key={current.reportKey}
      reportKey={current.reportKey}
      title="Sales & outstanding"
      breadcrumb={[{ label: 'Sales' }, { label: 'Sales & outstanding' }]}
      belowHeader={
        <Tabs value={current.value} onValueChange={setTab} className="mt-4">
          <TabsList variant="line">
            {visible.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      }
    />
  );
}
