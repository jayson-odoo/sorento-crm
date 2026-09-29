import { redirect } from 'next/navigation';

/**
 * The low stock report is always one plan's, at `/scm/low-stock-report/<run>`: opened from
 * Reorder planning > Actions or the daily email (owner hand test 26 Sep, W5; no sidebar item).
 * This bare path names no plan, so an old bookmark lands on Reorder planning to pick one.
 */
export default function LowStockReportPage() {
  redirect('/scm/reorder');
}
