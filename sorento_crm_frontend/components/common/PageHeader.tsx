'use client';

import { Fragment, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
} from '@/components/common/toolbar';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { useMenu } from '@/hooks/use-menu';
import { cn } from '@/lib/utils';

export interface PageHeaderCrumb {
  /** The label, which must read exactly as the sidebar reads (S5-02). */
  title: string;
  /** Omit for a grouping level the sidebar has no page for. */
  path?: string;
}

export interface PageHeaderProps {
  /** The page title. One scale, one component, every page (S5-01). */
  title: ReactNode;
  /**
   * The abbreviation the sidebar keeps, when the title spells it out (S5-03):
   * "GRN" over "Goods Receipt Notes".
   */
  eyebrow?: string;
  /**
   * Replaces the trail derived from the sidebar, for the pages the sidebar does
   * not name (a user's logs, a form's submissions). "Dashboards" is still the
   * first crumb; pass the trail below it.
   */
  crumbs?: PageHeaderCrumb[];
  /** The toolbar's right-hand side: Back on a detail page, Add on a list. */
  actions?: ReactNode;
  /**
   * Only where the title needs a wrapping rule of its own: a ticket number that
   * must not break mid-string, a supplier name that must truncate rather than
   * push the toolbar wide.
   */
  titleClassName?: string;
  /** A description or meta line, under the trail. */
  children?: ReactNode;
}

/** The root of every trail is the sidebar's own first entry, not "Home" (D11). */
const ROOT_CRUMB: PageHeaderCrumb = { title: 'Dashboards', path: '/' };

/**
 * Drops a crumb that repeats the title of the one before it, keeping the later
 * (deeper) one so its path survives: the sidebar nests "Products > Products >
 * All Products" and "Delivery Orders > Delivery Orders", which would otherwise
 * read as a stutter in the trail.
 */
function dedupe(crumbs: PageHeaderCrumb[]): PageHeaderCrumb[] {
  return crumbs.filter(
    (crumb, index) =>
      index === crumbs.length - 1 || crumbs[index + 1].title !== crumb.title,
  );
}

/**
 * The trail for a page, root included, from the chain the sidebar implies.
 *
 * A page the sidebar names ends on that entry. A page BELOW one - a record, a
 * create form, a nested tab - keeps the sidebar entry as a link and ends on the
 * page's own title, so the last crumb is always where the user actually is.
 * When the sidebar names nothing (an account page, a portal page) the trail is
 * the root plus the title.
 */
export function buildCrumbTrail(
  chain: PageHeaderCrumb[],
  pathname: string,
  title: ReactNode,
  override?: PageHeaderCrumb[],
): PageHeaderCrumb[] {
  if (override) {
    return dedupe([ROOT_CRUMB, ...override]);
  }

  const ownCrumb: PageHeaderCrumb[] =
    typeof title === 'string' && title.trim() ? [{ title: title.trim() }] : [];

  if (chain.length === 0) {
    return dedupe([ROOT_CRUMB, ...ownCrumb]);
  }

  const deepest = chain[chain.length - 1];
  const isBelowTheMenu = deepest.path !== pathname;

  return dedupe([ROOT_CRUMB, ...chain, ...(isBelowTheMenu ? ownCrumb : [])]);
}

/**
 * The one page header: eyebrow, title and trail on the left, actions on the
 * right (S5-01, S5-02).
 *
 * The trail comes from `MENU_SIDEBAR`, so a crumb always reads as the sidebar
 * reads and a renamed menu entry renames every trail that passes through it.
 */
export function PageHeader({
  title,
  eyebrow,
  crumbs,
  actions,
  titleClassName,
  children,
}: PageHeaderProps) {
  const pathname = usePathname() ?? '/';
  const { getBreadcrumb } = useMenu(pathname);
  const chain: PageHeaderCrumb[] = getBreadcrumb(MENU_SIDEBAR)
    .filter((item) => Boolean(item.title))
    .map((item) => ({ title: item.title as string, path: item.path }));
  const trail = buildCrumbTrail(chain, pathname, title, crumbs);

  return (
    <Toolbar>
      <ToolbarHeading className="min-w-0 gap-1">
        {eyebrow && (
          <span
            data-slot="page-header-eyebrow"
            className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
          >
            {eyebrow}
          </span>
        )}
        <h1
          className={cn(
            'min-w-0 break-words text-xl font-semibold text-foreground',
            titleClassName,
          )}
        >
          {title}
        </h1>
        <Breadcrumb>
          <BreadcrumbList>
            {trail.map((crumb, index) => {
              const isLast = index === trail.length - 1;

              return (
                <Fragment key={`${crumb.title}-${index}`}>
                  <BreadcrumbItem>
                    {isLast ? (
                      <BreadcrumbPage>{crumb.title}</BreadcrumbPage>
                    ) : crumb.path ? (
                      <BreadcrumbLink asChild>
                        <Link href={crumb.path}>{crumb.title}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <span>{crumb.title}</span>
                    )}
                  </BreadcrumbItem>
                  {!isLast && <BreadcrumbSeparator />}
                </Fragment>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>
        {children}
      </ToolbarHeading>
      {actions ? <ToolbarActions>{actions}</ToolbarActions> : null}
    </Toolbar>
  );
}

export default PageHeader;
