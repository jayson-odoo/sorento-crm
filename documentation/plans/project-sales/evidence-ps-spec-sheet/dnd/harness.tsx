import React from 'react';
import { createRoot } from 'react-dom/client';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';

function Strip({ wrapped, id }: { wrapped: boolean; id: string }) {
  const [items, setItems] = React.useState(['wc', 'basin', 'trap']);
  const cards = items.map((v) => (
    <SortableItem key={v} value={v}>
      <div style={{ position: 'relative', width: 140, height: 90, border: '1px solid #999', background: '#fff' }}>
        <span>{v}</span>
        <SortableItemHandle tabIndex={0} aria-label={`${id}-drag-${v}`}
          style={{ position: 'absolute', left: 0, top: 0, width: 140, height: 79 }} />
      </div>
    </SortableItem>
  ));
  return (
    <div style={{ display: 'flex', gap: 8, padding: 8 }}>
      <Sortable value={items} onValueChange={setItems} getItemValue={(v) => v} strategy="horizontal"
        className={wrapped ? undefined : 'flex gap-2'}>
        {wrapped ? <div style={{ display: 'flex', gap: 8 }}>{cards}</div> : cards}
      </Sortable>
      <output data-order={id}>{items.join(',')}</output>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <div>
    <Strip wrapped id="old" />
    <Strip wrapped={false} id="new" />
  </div>,
);
