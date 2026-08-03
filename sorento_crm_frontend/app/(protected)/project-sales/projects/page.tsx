import { redirect } from 'next/navigation';

/**
 * Projects folded into Pipeline.
 *
 * Pipeline already carries both views behind its own Board / Grid toggle, and its Grid
 * is the same list this page rendered. Two menu entries onto one screen is a choice the
 * user has to make and cannot get right, so the menu entry is gone.
 *
 * The route stays as a redirect rather than being deleted: bookmarks, older emails and
 * anything that linked here should land on the screen that replaced it, not on a 404.
 */
export default function ProjectsPage() {
  redirect('/project-sales/pipeline');
}
