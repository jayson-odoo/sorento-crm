import { useMemo, type CSSProperties } from 'react';
import { arrayMove } from '@dnd-kit/sortable';
import { DndContext, closestCenter, type DragEndEvent, MouseSensor, TouchSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core';
import { sortableKeyboardCoordinates, SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';

import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDataGrid } from '@/components/ui/data-grid';

type OrderedColumnItem = {
  id: string;
  label: string;
  canHide: boolean;
  isVisible: boolean;
  isPinned: boolean;
};

function DataGridColumnPanelItem({
  item,
}: {
  item: OrderedColumnItem;
}) {
  const { table } = useDataGrid();
  const column = table.getColumn(item.id);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    disabled: !column || item.isPinned,
  });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.85 : 1,
  };

  const label = item.label || item.id;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'flex items-center gap-2 px-2 py-1.5 rounded-md',
        'hover:bg-muted/30',
        item.isPinned && 'opacity-70',
      )}
    >
      <div className="cursor-grab select-none">
        <Button
          type="button"
          mode="icon"
          size="sm"
          variant="ghost"
          className="size-7"
          {...attributes}
          {...listeners}
          aria-label={`Drag to reorder ${label}`}
          disabled={item.isPinned}
        >
          <GripVertical className="size-4 opacity-60" />
        </Button>
      </div>

      <div className="flex-1 min-w-0">
        <div className="text-sm truncate">{label}</div>
      </div>

      {item.canHide ? (
        <Checkbox
          checked={item.isVisible}
          onCheckedChange={(checked) => column?.toggleVisibility(!!checked)}
          aria-label={`Toggle visibility for ${label}`}
        />
      ) : (
        <div className="w-[18px]" />
      )}
    </div>
  );
}

function DataGridColumnsPanel() {
  const { table, props, columnPreferences } = useDataGrid();

  const orderedIds = useMemo(() => {
    const stateOrder = table.getState().columnOrder as string[] | undefined;
    if (Array.isArray(stateOrder) && stateOrder.length > 0) return stateOrder;
    return table.getAllLeafColumns().map((c) => c.id);
  }, [table]);

  const items: OrderedColumnItem[] = useMemo(() => {
    return orderedIds
      .map((id) => {
        const col = table.getColumn(id);
        if (!col) return null;
        return {
          id,
          label: col.columnDef.meta?.headerTitle || col.id,
          canHide: col.getCanHide(),
          isVisible: col.getIsVisible(),
          isPinned: Boolean(col.getIsPinned()),
        } satisfies OrderedColumnItem;
      })
      .filter((x): x is OrderedColumnItem => Boolean(x));
  }, [orderedIds, table]);

  const sensors = useSensors(
    useSensor(MouseSensor, {}),
    useSensor(TouchSensor, {}),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const activeId = String(active.id);
    const overId = String(over.id);
    if (activeId === overId) return;

    const oldIndex = orderedIds.indexOf(activeId);
    const newIndex = orderedIds.indexOf(overId);
    if (oldIndex === -1 || newIndex === -1) return;

    table.setColumnOrder(arrayMove(orderedIds, oldIndex, newIndex));
  };

  if (!props.tableLayout?.columnsVisibility && !props.tableLayout?.columnsMovable) return null;

  return (
    <aside className="hidden lg:block w-[280px] border-l border-border pl-4">
      <div className="sticky top-6">
        <div className="flex items-center justify-between mb-3">
          <div className="font-medium">Columns</div>
          {columnPreferences?.resetToDefaults && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void columnPreferences.resetToDefaults?.()}
            >
              Reset
            </Button>
          )}
        </div>

        <DndContext
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
          sensors={sensors}
        >
          <SortableContext items={orderedIds} strategy={verticalListSortingStrategy}>
            <div className="space-y-1">
              {items.map((item) => (
                <DataGridColumnPanelItem key={item.id} item={item} />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </aside>
  );
}

export { DataGridColumnsPanel };

