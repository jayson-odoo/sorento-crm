import type { MenuConfig, MenuItem } from '@/config/types';

/** Hide menu branches tied to disabled tenant modules (null = still loading / error - show all). */
export function filterMenuByModule(items: MenuConfig, enabledModuleKeys: Set<string> | null): MenuConfig {
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
