import { redirect } from 'next/navigation';

/**
 * The combined "Pricing policy" screen is gone; series and price floors are two pages now.
 *
 * A redirect rather than a deletion: this path is in browser histories, in the sidebar of any
 * tab still open, and quite possibly in somebody's bookmarks. Landing them on Series - the
 * screen that page mostly WAS - beats a 404 that tells them nothing.
 */
export default function Page() {
  redirect('/project-sales/series');
}
