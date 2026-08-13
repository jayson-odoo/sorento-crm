import { MenuItem } from '@/config/types';
import { isUnderPath } from '@/lib/menu-path-match';

type MenuConfig = MenuItem[];

interface UseMenuReturn {
  isActive: (path: string | undefined) => boolean;
  hasActiveChild: (children: MenuItem[] | undefined) => boolean;
  isItemActive: (item: MenuItem) => boolean;
  getCurrentItem: (items: MenuConfig) => MenuItem | undefined;
  getBreadcrumb: (items: MenuConfig) => MenuItem[];
  getChildren: (items: MenuConfig, level: number) => MenuConfig | null;
}

export const useMenu = (pathname: string): UseMenuReturn => {
  const isActive = (path: string | undefined): boolean => {
    if (path && path === '/') {
      return path === pathname;
    }
    return !!path && isUnderPath(path, pathname);
  };

  const hasActiveChild = (children: MenuItem[] | undefined): boolean => {
    if (!children || !Array.isArray(children)) return false;
    return children.some(
      (child: MenuItem) =>
        (child.path && isActive(child.path)) ||
        (child.children && hasActiveChild(child.children)),
    );
  };

  const isItemActive = (item: MenuItem): boolean => {
    return (
      (item.path ? isActive(item.path) : false) ||
      (item.children ? hasActiveChild(item.children) : false)
    );
  };

  /**
   * The most specific match wins, not the first one found.
   *
   * A section landing page is a prefix of every page in its section (`/scm` is a prefix of
   * `/scm/sales-orders`), so first-match-wins named the landing page on every page below it:
   * the breadcrumb and the highlighted menu entry both pointed somewhere the user was not.
   */
  const getBreadcrumb = (items: MenuConfig): MenuItem[] => {
    let best: MenuItem[] = [];
    let bestLength = -1;

    const walk = (nodes: MenuItem[], chain: MenuItem[]): void => {
      for (const item of nodes) {
        const currentChain = [...chain, item];
        if (item.path && isActive(item.path) && item.path.length > bestLength) {
          best = currentChain;
          bestLength = item.path.length;
        }
        if (item.children && item.children.length > 0) {
          walk(item.children, currentChain);
        }
      }
    };

    walk(items, []);
    return best;
  };

  const getCurrentItem = (items: MenuConfig): MenuItem | undefined => {
    const chain = getBreadcrumb(items);
    return chain.length > 0 ? chain[chain.length - 1] : undefined;
  };

  const getChildren = (items: MenuConfig, level: number): MenuConfig | null => {
    const hasActiveChildAtLevel = (items: MenuConfig): boolean => {
      for (const item of items) {
        if (
          (item.path && item.path !== '' && isActive(item.path)) ||
          (item.children && hasActiveChildAtLevel(item.children))
        ) {
          return true;
        }
      }
      return false;
    };

    const findChildren = (
      items: MenuConfig,
      targetLevel: number,
      currentLevel: number = 0,
    ): MenuConfig | null => {
      for (const item of items) {
        if (item.children) {
          if (
            targetLevel === currentLevel &&
            hasActiveChildAtLevel(item.children)
          ) {
            return item.children;
          }
          const children = findChildren(
            item.children,
            targetLevel,
            currentLevel + 1,
          );
          if (children) {
            return children;
          }
        } else if (
          targetLevel === currentLevel &&
          item.path &&
          (item.path === pathname ||
            (item.path !== '/' &&
              item.path !== '' &&
              pathname.startsWith(item.path)))
        ) {
          return items;
        }
      }
      return null;
    };

    return findChildren(items, level);
  };

  return {
    isActive,
    hasActiveChild,
    isItemActive,
    getCurrentItem,
    getBreadcrumb,
    getChildren,
  };
};
