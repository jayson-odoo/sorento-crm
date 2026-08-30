/**
 * S5-01, S5-02, S5-03 - one page header, and a trail the sidebar writes.
 *
 * The trail is not typed per page any more, so what these assert is the RULE
 * that turns a pathname into crumbs: the sidebar's own chain, "Dashboards" at
 * the root, the deepest crumb marked current and nothing else, and a page that
 * lives BELOW a sidebar entry ending on its own title with the entry still a
 * link. Wording is asserted against `MENU_SIDEBAR` itself rather than a literal,
 * so renaming a menu entry renames the crumb and this test moves with it.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

import { PageHeader, buildCrumbTrail } from './PageHeader';

let pathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

beforeEach(() => {
  cleanup();
  pathname = '/';
});

/** The trail as the user reads it, in order. */
function trail(): string[] {
  const list = screen.getByRole('navigation', { name: 'breadcrumb' });
  return within(list)
    .getAllByRole('listitem')
    .filter((li) => li.getAttribute('data-slot') === 'breadcrumb-item')
    .map((li) => (li.textContent ?? '').trim());
}

describe('buildCrumbTrail', () => {
  const chain = [{ title: 'Prompts', path: '/system-management/ai-assistant/prompts' }];

  it('S5-02: an empty crumbs array is not an override', () => {
    // `crumbs={cond ? [...] : []}` is the natural way to write a conditional
    // trail; treating [] as "the trail is just the root" would silently throw
    // the sidebar's own chain away.
    expect(
      buildCrumbTrail(chain, '/system-management/ai-assistant/prompts', 'Prompts', []),
    ).toEqual([
      { title: 'Dashboards', path: '/' },
      { title: 'Prompts', path: '/system-management/ai-assistant/prompts' },
    ]);
  });

  it('S5-02: crumbTitle names the page a node title cannot', () => {
    expect(
      buildCrumbTrail(
        chain,
        '/system-management/ai-assistant/prompts/router.plan',
        null,
        undefined,
        'router.plan',
      ).at(-1),
    ).toEqual({ title: 'router.plan' });
  });

  it('S5-02: a string title still wins over crumbTitle', () => {
    expect(
      buildCrumbTrail(
        chain,
        '/system-management/ai-assistant/prompts/router.plan',
        'router.plan',
        undefined,
        'ignored',
      ).at(-1),
    ).toEqual({ title: 'router.plan' });
  });

  it('S5-02: neither a string title nor a crumbTitle ends on the sidebar entry', () => {
    expect(
      buildCrumbTrail(
        chain,
        '/system-management/ai-assistant/prompts/router.plan',
        null,
      ).at(-1),
    ).toEqual(chain[0]);
  });
});

describe('PageHeader', () => {
  it('S5-01: the title is the page\'s only h1, at one scale', () => {
    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toBe('Administrative Users');
    expect(headings[0].className).toContain('text-xl');
  });

  it('S5-02: a list page reads the sidebar chain, root first', () => {
    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    expect(trail()).toEqual([
      'Dashboards',
      'Users & Access',
      'People',
      'Administrative Users',
    ]);
  });

  it('S5-02: the root crumb is "Dashboards" and links to the dashboard', () => {
    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    const home = screen.getByRole('link', { name: 'Dashboards' });
    expect(home.getAttribute('href')).toBe('/');
    expect(screen.queryByRole('link', { name: 'Home' })).toBeNull();
  });

  it('S5-02: only the last crumb is the current page', () => {
    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    const current = screen
      .getByRole('navigation', { name: 'breadcrumb' })
      .querySelectorAll('[aria-current="page"]');
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toBe('Administrative Users');
  });

  it('S5-02: a grouping level the sidebar has no page for is not a link', () => {
    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    // "Users & Access" and "People" are sidebar groups, not pages.
    expect(screen.queryByRole('link', { name: 'Users & Access' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'People' })).toBeNull();
    expect(trail()).toContain('Users & Access');
  });

  it('S5-02: a record page ends on its own title, the list staying a link', () => {
    pathname = '/order-management/orders/6d5f';
    render(<PageHeader title="Delivery Order" />);

    expect(trail()).toEqual(['Dashboards', 'Delivery Orders', 'Delivery Order']);
    expect(
      screen.getByRole('link', { name: 'Delivery Orders' }).getAttribute('href'),
    ).toBe('/order-management/orders');
  });

  it('S5-02: a create page ends on its own title', () => {
    pathname = '/master-data-management/products/new';
    render(<PageHeader title="Create Product" />);

    expect(trail()).toEqual([
      'Dashboards',
      'Products',
      'All Products',
      'Create Product',
    ]);
  });

  it('S5-02: a repeated sidebar level does not stutter in the trail', () => {
    // The sidebar nests "Delivery Orders > Delivery Orders"; the trail says it
    // once.
    pathname = '/order-management/orders';
    render(<PageHeader title="Delivery Orders" />);

    expect(trail()).toEqual(['Dashboards', 'Delivery Orders']);
  });

  it('S5-02: crumb wording equals sidebar wording', async () => {
    const { MENU_SIDEBAR } = await import('@/config/menu.config');
    const titles = new Set<string>();
    const walk = (items: typeof MENU_SIDEBAR) => {
      for (const item of items) {
        if (item.title) titles.add(item.title);
        if (item.children) walk(item.children);
      }
    };
    walk(MENU_SIDEBAR);

    pathname = '/user-management/users';
    render(<PageHeader title="Administrative Users" />);

    for (const crumb of trail()) {
      expect(titles.has(crumb), crumb).toBe(true);
    }
  });

  it('S5-02: the override replaces the trail below the root', () => {
    pathname = '/user-management/users/u-1/logs';
    render(
      <PageHeader
        title="Activity log"
        crumbs={[
          { title: 'Administrative Users', path: '/user-management/users' },
          { title: 'Activity log' },
        ]}
      />,
    );

    expect(trail()).toEqual([
      'Dashboards',
      'Administrative Users',
      'Activity log',
    ]);
    expect(
      screen
        .getByRole('link', { name: 'Administrative Users' })
        .getAttribute('href'),
    ).toBe('/user-management/users');
  });

  it('S5-02: a page the sidebar does not name still has a trail', () => {
    pathname = '/account/home/get-started';
    render(<PageHeader title="Get started" />);

    expect(trail()).toEqual(['Dashboards', 'Get started']);
  });

  it('S5-02: the dashboard itself is the only crumb', () => {
    pathname = '/';
    render(<PageHeader title="Dashboards" />);

    expect(trail()).toEqual(['Dashboards']);
  });

  it('S5-03: the abbreviation the sidebar keeps rides above the spelt-out title', () => {
    pathname = '/procurement-management/grn';
    render(<PageHeader title="Goods Receipt Notes" eyebrow="GRN" />);

    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Goods Receipt Notes',
    );
    expect(
      document.querySelector('[data-slot="page-header-eyebrow"]')?.textContent,
    ).toBe('GRN');
    // D11: the sidebar keeps the abbreviation, so the crumb does too.
    expect(trail().at(-1)).toBe('GRN');
  });

  it('S5-02: a node title names its own crumb through crumbTitle', () => {
    // The prompt detail page: the title is a name with a Dormant badge beside
    // it, so the trail cannot read the title and would otherwise end on
    // "Prompts" - the entry ABOVE the page, marked as the current one.
    pathname = '/system-management/ai-assistant/prompts/router.plan';
    render(
      <PageHeader
        title={
          <span>
            <span>router.plan</span>
            <span>Dormant</span>
          </span>
        }
        crumbTitle="router.plan"
      />,
    );

    expect(trail().at(-1)).toBe('router.plan');
    expect(
      screen.getByRole('link', { name: 'Prompts' }).getAttribute('href'),
    ).toBe('/system-management/ai-assistant/prompts');
  });

  it('S5-02: a node title with no crumbTitle still ends on the sidebar entry', () => {
    pathname = '/system-management/ai-assistant/prompts/router.plan';
    render(<PageHeader title={<span>router.plan</span>} />);

    expect(trail().at(-1)).toBe('Prompts');
  });

  it('renders the actions it is given', () => {
    pathname = '/order-management/orders/6d5f';
    render(
      <PageHeader
        title="Delivery Order"
        actions={<button type="button">Back to delivery orders</button>}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Back to delivery orders' }),
    ).toBeInTheDocument();
  });
});
