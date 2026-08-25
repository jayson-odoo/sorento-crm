'use client';

import SalesOrdersGrid from './SalesOrdersGrid';

/**
 * The Sales Orders list: the whole book, with nothing pinned.
 *
 * The table itself is `SalesOrdersGrid`, which the sales-agent record's Sales orders tab
 * renders too. This file stays as the list's own name so the route and its suites keep
 * addressing the screen rather than the component it is built from.
 */
export default function SalesOrdersList() {
  return <SalesOrdersGrid />;
}
