'use client';

import { Boxes, Package, Truck } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import type { Perspective } from '../types/scm.types';

const OPTIONS: { value: Perspective; label: string; icon: typeof Package }[] = [
  { value: 'product', label: 'Product', icon: Package },
  { value: 'warehouse', label: 'Warehouse', icon: Boxes },
  { value: 'supplier', label: 'Supplier', icon: Truck },
];

export function PerspectiveToggle({
  value,
  onChange,
}: {
  value: Perspective;
  onChange: (v: Perspective) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      value={value}
      onValueChange={(v) => v && onChange(v as Perspective)}
    >
      {OPTIONS.map((opt) => {
        const Icon = opt.icon;
        return (
          <ToggleGroupItem key={opt.value} value={opt.value} className="gap-1.5 px-3">
            <Icon className="size-4" aria-hidden />
            {opt.label}
          </ToggleGroupItem>
        );
      })}
    </ToggleGroup>
  );
}
