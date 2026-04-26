/**
 * Per-module FE asset registry.
 *
 * Each migrated module ships a directory under `modules/<key>/` containing JSON metadata
 * (menu, routes, purge tables). Because Next.js builds are static, a generated registry
 * file lists every module's assets via static imports — Webpack inlines them at build time.
 *
 * To add a module: drop a folder here with `menu.json`, `routes.json`, `purge_tables.json`,
 * then append it to `MODULE_REGISTRY` below. Phase 8 (upload flow) edits this file
 * automatically when a zip is dropped into the App Store.
 */

import type { LucideIcon } from 'lucide-react';

export interface ModuleMenuChildJson {
  title: string;
  path?: string;
  permissionSlugs?: string[];
}

export interface ModuleMenuJson {
  title: string;
  path?: string;
  iconName?: string;
  moduleKey: string;
  permissionSlugs?: string[];
  children?: ModuleMenuChildJson[];
}

export interface ModuleRouteJson {
  prefix: string;
  moduleKey: string;
}

export interface ModulePurgeTablesJson {
  moduleKey: string;
  tables: string[];
  description?: string;
}

export interface ModuleAsset {
  key: string;
  version?: string;
  menu?: ModuleMenuJson;
  routes?: ModuleRouteJson[];
  purgeTables?: ModulePurgeTablesJson;
}

export const MODULE_REGISTRY: ModuleAsset[] = [
  // Migrated modules append here. Empty by default (Phase 1-3 are infra-only).
];

export function moduleRoutePrefixes(): { prefix: string; moduleKey: string }[] {
  return MODULE_REGISTRY.flatMap((m) => m.routes ?? []);
}

export function modulePurgeTables(): Record<string, { tables: string[]; description?: string }> {
  const out: Record<string, { tables: string[]; description?: string }> = {};
  for (const m of MODULE_REGISTRY) {
    if (m.purgeTables) {
      out[m.purgeTables.moduleKey] = {
        tables: m.purgeTables.tables,
        description: m.purgeTables.description,
      };
    }
  }
  return out;
}

export function modulesWithDataPurge(): string[] {
  return MODULE_REGISTRY.filter((m) => m.purgeTables).map((m) => m.purgeTables!.moduleKey);
}

export type { LucideIcon };
