'use client';

import { JSX, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { isSuperadminUser } from '@/lib/is-superadmin';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { injectPublishedWorkflowForms } from '@/config/workflow-forms-dynamic-menu';
import { MenuConfig, MenuItem } from '@/config/types';
import { usePublishedWorkflowDefinitionsForSubmissionQuery } from '@/app/(protected)/workflow-forms-management/hooks/useWorkflowForms';
import { cn } from '@/lib/utils';
import { usePermissions, useHasAnyPermission } from '@/hooks/usePermissions';
import { WORKFLOW_PUBLISHED_FOR_SUBMISSION_PERMISSIONS } from '@/config/workflow-forms-dynamic-menu';
import { useTenantModules } from '@/hooks/useTenantModules';
import {
  AccordionMenu,
  AccordionMenuClassNames,
  AccordionMenuGroup,
  AccordionMenuItem,
  AccordionMenuLabel,
  AccordionMenuSub,
  AccordionMenuSubContent,
  AccordionMenuSubTrigger,
} from '@/components/ui/accordion-menu';
import { Badge } from '@/components/ui/badge';
import { QuickAccessBlock } from './quick-access-block';
import { MenuItemPinButton } from './menu-item-pin-button';

/** Filter menu items by permission: hide items that require a permission the user doesn't have; recurse into children. */
function filterMenuByPermission(items: MenuConfig, permissionSet: Set<string>): MenuConfig {
  return items.filter((item: MenuItem) => {
    if (item.heading) return true;
    if (item.permissionsAny?.length) {
      if (!item.permissionsAny.some((p) => permissionSet.has(p))) return false;
    } else if (item.permission && !permissionSet.has(item.permission)) {
      return false;
    }
    if (item.children?.length) {
      const filtered = filterMenuByPermission(item.children, permissionSet);
      return filtered.length > 0;
    }
    return true;
  }).map((item: MenuItem) => {
    if (item.children?.length) {
      return { ...item, children: filterMenuByPermission(item.children, permissionSet) };
    }
    return item;
  });
}

/** Hide superadmin-only entries from non-superadmins. `isSuperadmin` null = still loading — show all (avoids flicker for real superadmins). */
function filterMenuBySuperadmin(items: MenuConfig, isSuperadmin: boolean | null): MenuConfig {
  if (isSuperadmin === null || isSuperadmin) return items;
  return items
    .filter((item: MenuItem) => {
      if (item.heading) return true;
      if (item.superadminOnly) return false;
      if (item.children?.length) {
        return filterMenuBySuperadmin(item.children, isSuperadmin).length > 0;
      }
      return true;
    })
    .map((item: MenuItem) =>
      item.children?.length
        ? { ...item, children: filterMenuBySuperadmin(item.children, isSuperadmin) }
        : item,
    );
}

/** Hide menu branches tied to disabled tenant modules (null = still loading / error — show all). */
function filterMenuByModule(items: MenuConfig, enabledModuleKeys: Set<string> | null): MenuConfig {
  if (!enabledModuleKeys) return items;
  return items
    .filter((item: MenuItem) => {
      if (item.heading) return true;
      if (item.moduleKey && !enabledModuleKeys.has(item.moduleKey)) return false;
      if (item.children?.length) {
        const filtered = filterMenuByModule(item.children, enabledModuleKeys);
        return filtered.length > 0;
      }
      return true;
    })
    .map((item: MenuItem) => {
      if (item.children?.length) {
        return { ...item, children: filterMenuByModule(item.children, enabledModuleKeys) };
      }
      return item;
    });
}

export function SidebarMenu() {
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const isSuperadmin = status === 'loading' ? null : isSuperadminUser(session?.user);
  const { permissionSet, isLoading } = usePermissions();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const wfModuleEnabled = enabledModuleKeys?.has('workflow_forms') ?? false;
  /** Avoid calling published-for-submission without RBAC — global QueryCache onError would toast 403 on every page. */
  const canFetchPublishedWorkflowForms = useHasAnyPermission(
    [...WORKFLOW_PUBLISHED_FOR_SUBMISSION_PERMISSIONS],
  );
  const { data: publishedFormsRes } = usePublishedWorkflowDefinitionsForSubmissionQuery({
    enabled: wfModuleEnabled && !modulesLoading && canFetchPublishedWorkflowForms,
  });

  const menuWithPublishedForms = useMemo(
    () => injectPublishedWorkflowForms(MENU_SIDEBAR, publishedFormsRes?.data ?? []),
    [publishedFormsRes?.data],
  );

  const effectiveMenu = useMemo(() => {
    const bySuper = filterMenuBySuperadmin(menuWithPublishedForms, isSuperadmin);
    if (isLoading) return bySuper;
    const byPerm = filterMenuByPermission(bySuper, permissionSet);
    if (modulesLoading) return byPerm;
    return filterMenuByModule(byPerm, enabledModuleKeys);
  }, [
    permissionSet,
    isLoading,
    enabledModuleKeys,
    modulesLoading,
    menuWithPublishedForms,
    isSuperadmin,
  ]);

  // Memoize matchPath to prevent unnecessary re-renders
  const matchPath = useCallback(
    (path: string): boolean =>
      path === pathname || (path.length > 1 && pathname.startsWith(path)),
    [pathname],
  );

  // Global classNames for consistent styling
  const classNames: AccordionMenuClassNames = {
    root: 'lg:ps-1 space-y-3',
    group: 'gap-px',
    label:
      'uppercase text-xs font-medium text-muted-foreground/70 pt-2.25 pb-px',
    separator: '',
    item: 'h-8 hover:bg-transparent text-accent-foreground hover:text-primary data-[selected=true]:text-primary data-[selected=true]:bg-muted data-[selected=true]:font-medium',
    sub: '',
    subTrigger:
      'h-8 hover:bg-transparent text-accent-foreground hover:text-primary data-[selected=true]:text-primary data-[selected=true]:bg-muted data-[selected=true]:font-medium',
    subContent: 'py-0',
    indicator: '',
  };

  const buildMenu = (items: MenuConfig): JSX.Element[] => {
    return items.map((item: MenuItem, index: number) => {
      if (item.heading) {
        return buildMenuHeading(item, index);
      } else if (item.disabled) {
        return buildMenuItemRootDisabled(item, index);
      } else {
        return buildMenuItemRoot(item, index);
      }
    });
  };

  const buildMenuItemRoot = (item: MenuItem, index: number): JSX.Element => {
    if (item.children) {
      return (
        <AccordionMenuSub key={index} value={item.path || `root-${index}`}>
          <AccordionMenuSubTrigger className="text-sm font-medium">
            {item.icon && <item.icon data-slot="accordion-menu-icon" />}
            <span data-slot="accordion-menu-title">{item.title}</span>
          </AccordionMenuSubTrigger>
          <AccordionMenuSubContent
            type="single"
            collapsible
            parentValue={item.path || `root-${index}`}
            className="ps-6"
          >
            <AccordionMenuGroup>
              {buildMenuItemChildren(item.children, 1)}
            </AccordionMenuGroup>
          </AccordionMenuSubContent>
        </AccordionMenuSub>
      );
    } else {
      return (
        <AccordionMenuItem
          key={index}
          value={item.path || ''}
          className="text-sm font-medium group"
        >
          <Link
            href={item.path || '#'}
            prefetch={false}
            className="flex items-center grow gap-2 min-w-0"
          >
            {item.icon && <item.icon data-slot="accordion-menu-icon" className="shrink-0" />}
            <span data-slot="accordion-menu-title" className="truncate">{item.title}</span>
            {item.path && <MenuItemPinButton path={item.path} title={item.title} className="ms-auto" />}
          </Link>
        </AccordionMenuItem>
      );
    }
  };

  const buildMenuItemRootDisabled = (
    item: MenuItem,
    index: number,
  ): JSX.Element => {
    return (
      <AccordionMenuItem
        key={index}
        value={`disabled-${index}`}
        className="text-sm font-medium"
      >
        {item.icon && <item.icon data-slot="accordion-menu-icon" />}
        <span data-slot="accordion-menu-title">{item.title}</span>
        {item.disabled && (
          <Badge variant="secondary" size="sm" className="ms-auto me-[-10px]">
            Soon
          </Badge>
        )}
      </AccordionMenuItem>
    );
  };

  const buildMenuItemChildren = (
    items: MenuConfig,
    level: number = 0,
  ): JSX.Element[] => {
    return items.map((item: MenuItem, index: number) => {
      if (item.disabled) {
        return buildMenuItemChildDisabled(item, index, level);
      } else {
        return buildMenuItemChild(item, index, level);
      }
    });
  };

  const buildMenuItemChild = (
    item: MenuItem,
    index: number,
    level: number = 0,
  ): JSX.Element => {
    if (item.children) {
      return (
        <AccordionMenuSub
          key={index}
          value={item.path || `child-${level}-${index}`}
        >
          <AccordionMenuSubTrigger className="text-[13px]">
            {item.collapse ? (
              <span className="text-muted-foreground">
                <span className="hidden [[data-state=open]>span>&]:inline">
                  {item.collapseTitle}
                </span>
                <span className="inline [[data-state=open]>span>&]:hidden">
                  {item.expandTitle}
                </span>
              </span>
            ) : (
              item.title
            )}
          </AccordionMenuSubTrigger>
          <AccordionMenuSubContent
            type="single"
            collapsible
            parentValue={item.path || `child-${level}-${index}`}
            className={cn(
              'ps-4',
              !item.collapse && 'relative',
              !item.collapse && (level > 0 ? '' : ''),
            )}
          >
            <AccordionMenuGroup>
              {buildMenuItemChildren(
                item.children,
                item.collapse ? level : level + 1,
              )}
            </AccordionMenuGroup>
          </AccordionMenuSubContent>
        </AccordionMenuSub>
      );
    } else {
      return (
        <AccordionMenuItem
          key={index}
          value={item.path || ''}
          className="text-[13px] group"
        >
          <div className="flex items-center gap-1 min-w-0 w-full">
            <Link href={item.path || '#'} prefetch={false} className="flex-1 min-w-0 truncate">
              {item.title}
            </Link>
            {item.path && (
              <MenuItemPinButton path={item.path} title={item.title} size="sm" />
            )}
          </div>
        </AccordionMenuItem>
      );
    }
  };

  const buildMenuItemChildDisabled = (
    item: MenuItem,
    index: number,
    level: number = 0,
  ): JSX.Element => {
    return (
      <AccordionMenuItem
        key={index}
        value={`disabled-child-${level}-${index}`}
        className="text-[13px]"
      >
        <span data-slot="accordion-menu-title">{item.title}</span>
        {item.disabled && (
          <Badge variant="secondary" size="sm" className="ms-auto me-[-10px]">
            Soon
          </Badge>
        )}
      </AccordionMenuItem>
    );
  };

  const buildMenuHeading = (item: MenuItem, index: number): JSX.Element => {
    return <AccordionMenuLabel key={index}>{item.heading}</AccordionMenuLabel>;
  };

  const userManagementIndex = useMemo(
    () => effectiveMenu.findIndex((item) => !item.heading && item.title === 'User Management'),
    [effectiveMenu]
  );
  const indexToSplit = userManagementIndex >= 0 ? userManagementIndex : effectiveMenu.length;
  const menuBefore = useMemo(() => effectiveMenu.slice(0, indexToSplit), [effectiveMenu, indexToSplit]);
  const menuAfter = useMemo(() => effectiveMenu.slice(indexToSplit), [effectiveMenu, indexToSplit]);

  return (
    <div className="kt-scrollable-y-hover flex grow shrink-0 py-5 px-5 lg:max-h-[calc(100vh-5.5rem)]">
      <AccordionMenu
        selectedValue={pathname}
        matchPath={matchPath}
        type="single"
        collapsible
        classNames={classNames}
        defaultExpandedValue="quick-access"
      >
        {buildMenu(menuBefore)}
        <QuickAccessBlock />
        {buildMenu(menuAfter)}
      </AccordionMenu>
    </div>
  );
}
