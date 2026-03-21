import { type LucideIcon } from 'lucide-react';

export interface MenuItem {
  title?: string;
  icon?: LucideIcon;
  path?: string;
  rootPath?: string;
  childrenIndex?: number;
  heading?: string;
  children?: MenuConfig;
  disabled?: boolean;
  collapse?: boolean;
  collapseTitle?: string;
  expandTitle?: string;
  badge?: string;
  separator?: boolean;
  /** RBAC: permission slug required to view this item (e.g. "order_management.orders.view"). If set, item is hidden when user lacks this permission. */
  permission?: string;
  /**
   * Installable module key from backend App Store (e.g. "inventory").
   * When tenant modules are loaded, this branch is hidden if the module is disabled.
   */
  moduleKey?: string;
}

export type MenuConfig = MenuItem[];

export interface Settings {
  container: 'fixed' | 'fluid';
  layout: string;
  layouts: {
    demo1: {
      sidebarCollapse: boolean;
      sidebarTheme: 'light' | 'dark';
    };
    demo2: {
      headerSticky: boolean;
      headerStickyOffset: number;
    };
    demo5: {
      headerSticky: boolean;
      headerStickyOffset: number;
    };
    demo7: {
      headerSticky: boolean;
      headerStickyOffset: number;
    };
    demo9: {
      headerSticky: boolean;
      headerStickyOffset: number;
    };
  };
}
