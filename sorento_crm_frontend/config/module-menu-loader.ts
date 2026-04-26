/**
 * Build-time bridge between `modules/registry.ts` (per-module JSON) and `menu.config.tsx`.
 *
 * Resolves `iconName` strings to Lucide React components and produces `MenuItem`-shaped
 * entries that menu.config.tsx can spread into its sidebar arrays.
 */

import * as Lucide from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { MODULE_REGISTRY, type ModuleMenuJson } from '@/modules/registry';
import type { MenuItem } from '@/config/types';

const FALLBACK_ICON: LucideIcon = (Lucide as unknown as { Square: LucideIcon }).Square;

function resolveIcon(name?: string): LucideIcon {
  if (!name) return FALLBACK_ICON;
  const candidate = (Lucide as unknown as Record<string, LucideIcon | undefined>)[name];
  return candidate ?? FALLBACK_ICON;
}

function toMenuItem(json: ModuleMenuJson): MenuItem {
  const item: MenuItem = {
    title: json.title,
    icon: resolveIcon(json.iconName),
    moduleKey: json.moduleKey,
  } as MenuItem;
  if (json.path) (item as { path?: string }).path = json.path;
  if (json.permissionSlugs) (item as { permissionSlugs?: string[] }).permissionSlugs = json.permissionSlugs;
  if (json.children?.length) {
    (item as { children?: MenuItem[] }).children = json.children.map((child) => ({
      title: child.title,
      path: child.path,
      permissionSlugs: child.permissionSlugs,
    } as MenuItem));
  }
  return item;
}

export function discoveredMenuItems(): MenuItem[] {
  return MODULE_REGISTRY.filter((m) => m.menu).map((m) => toMenuItem(m.menu!));
}
