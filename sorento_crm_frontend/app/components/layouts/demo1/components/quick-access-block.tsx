'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Star, GripVertical, PinOff, Plus, Search, Folder, FileText } from 'lucide-react';
import { AccordionMenuSub, AccordionMenuSubContent, AccordionMenuSubTrigger, AccordionMenuGroup } from '@/components/ui/accordion-menu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import { cn } from '@/lib/utils';
import { flattenMenuItems, getTitleForPath } from '@/lib/menu-utils';
import { moduleKeyForPath } from '@/lib/route-module-map';
import { useTenantModules } from '@/hooks/useTenantModules';
import { MENU_SIDEBAR } from '@/config/menu.config';
import {
  useQuickAccess,
  useAddQuickAccess,
  useRemoveQuickAccess,
  useReorderQuickAccess,
  type QuickAccessItem,
} from '@/hooks/useQuickAccess';
import { useHasAnyPermission } from '@/hooks/usePermissions';

const QUICK_ACCESS_VALUE = 'quick-access';

export function QuickAccessBlock() {
  const canUseQuickAccess = useHasAnyPermission(['menu.quick_access.pin', 'menu.quick_access.unpin']);
  const { data: items = [], isLoading } = useQuickAccess();
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const addMutation = useAddQuickAccess();
  const removeMutation = useRemoveQuickAccess();
  const reorderMutation = useReorderQuickAccess();

  const flattened = useMemo(() => flattenMenuItems(MENU_SIDEBAR), []);
  const pinnedPaths = useMemo(() => new Set(items.map((i) => i.path)), [items]);
  const pinnableMenuItems = useMemo(() => {
    let list = flattened.filter((m) => !pinnedPaths.has(m.path));
    if (!modulesLoading && enabledModuleKeys) {
      list = list.filter((m) => {
        const mk = moduleKeyForPath(m.path);
        if (!mk) return true;
        return enabledModuleKeys.has(mk);
      });
    }
    return list;
  }, [flattened, pinnedPaths, enabledModuleKeys, modulesLoading]);

  const [addShortcutSearch, setAddShortcutSearch] = useState('');
  const filteredPinnableItems = useMemo(() => {
    const q = addShortcutSearch.trim().toLowerCase();
    if (!q) return pinnableMenuItems;
    return pinnableMenuItems.filter(
      (m) =>
        m.title.toLowerCase().includes(q) || m.path.toLowerCase().includes(q)
    );
  }, [pinnableMenuItems, addShortcutSearch]);

  const displayTitle = (item: QuickAccessItem) =>
    getTitleForPath(flattened, item.path, item.label);

  /** True if this quick access entry is a pinned folder (attachment directory). */
  const isFolderPin = (item: QuickAccessItem) =>
    /[?&]directoryId=/i.test(item.path);

  const handleReorder = (newOrder: QuickAccessItem[]) => {
    const orderedIds = newOrder.map((i) => i.id);
    reorderMutation.mutate(orderedIds);
  };

  if (!canUseQuickAccess) return null;

  return (
    <AccordionMenuSub key={QUICK_ACCESS_VALUE} value={QUICK_ACCESS_VALUE}>
      <AccordionMenuSubTrigger className="text-sm font-medium">
        <Star data-slot="accordion-menu-icon" className="size-4 shrink-0" />
        <span data-slot="accordion-menu-title">Quick Access</span>
      </AccordionMenuSubTrigger>
      <AccordionMenuSubContent
        type="single"
        collapsible
        parentValue={QUICK_ACCESS_VALUE}
        className="ps-6"
      >
        <AccordionMenuGroup>
          <div className="flex items-center gap-1 px-1 pb-1">
            <DropdownMenu onOpenChange={(open) => !open && setAddShortcutSearch('')}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 text-[13px] gap-1">
                  <Plus className="size-3.5" />
                  Add shortcut
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64 p-0" onCloseAutoFocus={(e) => e.preventDefault()}>
                <div className="p-2 border-b">
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
                    <Input
                      placeholder="Search menu..."
                      value={addShortcutSearch}
                      onChange={(e) => setAddShortcutSearch(e.target.value)}
                      className="pl-8 h-8 text-sm"
                      onKeyDown={(e) => e.stopPropagation()}
                    />
                  </div>
                </div>
                <div className="max-h-[min(50vh,320px)] overflow-y-auto">
                  {pinnableMenuItems.length === 0 ? (
                    <div className="px-2 py-3 text-[13px] text-muted-foreground text-center">
                      All menu items are already pinned.
                    </div>
                  ) : filteredPinnableItems.length === 0 ? (
                    <div className="px-2 py-3 text-[13px] text-muted-foreground text-center">
                      No matches for &quot;{addShortcutSearch}&quot;
                    </div>
                  ) : (
                    filteredPinnableItems.map((m) => (
                      <DropdownMenuItem
                        key={m.path}
                        onClick={() => addMutation.mutate({ path: m.path })}
                        className="cursor-pointer"
                      >
                        {m.title}
                      </DropdownMenuItem>
                    ))
                  )}
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          {isLoading ? (
            <div className="text-[13px] text-muted-foreground py-1">Loading…</div>
          ) : items.length === 0 ? (
            <div className="text-[13px] text-muted-foreground py-1 px-1">
              Pin menu items or folders for quick access.
            </div>
          ) : (
            <Sortable<QuickAccessItem>
              value={items}
              onValueChange={handleReorder}
              getItemValue={(item) => item.id}
              className="flex flex-col gap-px"
            >
              {items.map((item) => (
                <SortableItem key={item.id} value={item.id} className="text-[13px]">
                  <div
                    className={cn(
                      'flex items-center gap-1.5 min-w-0 rounded-md h-8 px-1',
                      'hover:bg-muted/60'
                    )}
                  >
                    <SortableItemHandle className="shrink-0 p-0.5 rounded cursor-grab active:cursor-grabbing text-muted-foreground">
                      <GripVertical className="size-4" />
                    </SortableItemHandle>
                    {isFolderPin(item) ? (
                      <Folder className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    ) : (
                      <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    )}
                    <Link
                      href={item.path}
                      className="flex-1 min-w-0 truncate hover:text-primary"
                      title={displayTitle(item)}
                    >
                      {displayTitle(item)}
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      aria-label="Remove from quick access"
                      onClick={(e) => {
                        e.preventDefault();
                        removeMutation.mutate(item.id);
                      }}
                    >
                      <PinOff className="size-3.5" />
                    </Button>
                  </div>
                </SortableItem>
              ))}
            </Sortable>
          )}
        </AccordionMenuGroup>
      </AccordionMenuSubContent>
    </AccordionMenuSub>
  );
}
