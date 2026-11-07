'use client';

/**
 * The tags of a request that will print without some of their feature icons, because the icons
 * do not fit the layer box (crew pass, 5 Nov). One warning above the preview; nothing when every
 * icon fits. Drawn by `DesignViewer` (staff Design, portal live preview, self-approval) and by the
 * request designer.
 */
import { Alert, AlertDescription } from '@/components/ui/alert';
import type { FeatureIconDrop } from '@/lib/dealer-kit/feature-icon-drops';
import type { AccessoryDrop } from '@/lib/dealer-kit/accessory-drops';

export function featureIconDropLine({ tagLabel, dropped }: FeatureIconDrop): string {
  return dropped === 1
    ? `Tag ${tagLabel}: 1 feature icon does not fit its box`
    : `Tag ${tagLabel}: ${dropped} feature icons do not fit their box`;
}

/** PRICETAG-ACCESSORIES (A6): the same line for an accessories box too small for its list. */
export function accessoryDropLine({ tagLabel, dropped }: AccessoryDrop): string {
  return dropped === 1
    ? `Tag ${tagLabel}: 1 accessory does not fit its box`
    : `Tag ${tagLabel}: ${dropped} accessories do not fit their box`;
}

export function FeatureIconDropWarning({
  drops,
  accessoryDrops = [],
  className,
}: {
  drops: FeatureIconDrop[];
  accessoryDrops?: AccessoryDrop[];
  className?: string;
}) {
  if (drops.length === 0 && accessoryDrops.length === 0) return null;
  return (
    <Alert variant="warning" size="sm" role="status" className={className}>
      <AlertDescription className="flex flex-col gap-0.5">
        {drops.map((drop) => (
          <span key={drop.tagLabel}>{featureIconDropLine(drop)}</span>
        ))}
        {accessoryDrops.map((drop) => (
          <span key={`acc-${drop.tagLabel}`}>{accessoryDropLine(drop)}</span>
        ))}
      </AlertDescription>
    </Alert>
  );
}
