'use client';

import Link from 'next/link';

import { AttachmentImage } from '@/components/common/AttachmentImage';
import { withTab } from '@/hooks/useUrlTab';

interface SpecValueIcon {
  id: string;
  name: string;
  url: string | null;
}

/**
 * The price-tag icons one spec value carries, inline after the value (SPEC-VALUE-ICONS 1a).
 *
 * Drawn through the one image component (owner 3 Nov). The tooltip is the icon's name. For a
 * `dealer_kit.library.manage` holder each icon opens the spec key's Choices and words tab, where
 * the value's icons are set (2a); for anyone else it is a tooltip only. No icon, no element (5a).
 */
export function SpecValueIcons({
  specKey,
  label,
  icons,
  reasons = {},
  canManage,
}: {
  specKey: string;
  label: string;
  icons: SpecValueIcon[];
  reasons?: Record<string, string>;
  canManage: boolean;
}) {
  if (icons.length === 0) return null;
  const href = withTab(
    `/master-data-management/product-specifications/${specKey}`,
    'choices',
  );
  return (
    <span className="contents" data-spec-icons={specKey}>
      <span className="flex shrink-0 items-center gap-1">
        {icons.map((icon) => {
          const picture = (
            <AttachmentImage
              url={icon.url}
              size="original"
              alt={icon.name}
              className="size-6 object-contain"
            />
          );
          return canManage ? (
            <Link
              key={icon.id}
              href={href}
              title={icon.name}
              aria-label={`${icon.name}, open ${label}`}
              data-spec-icon={icon.id}
              className="inline-flex shrink-0 rounded-sm outline-none hover:ring-1 hover:ring-border focus-visible:ring-2 focus-visible:ring-ring"
            >
              {picture}
            </Link>
          ) : (
            <span
              key={icon.id}
              title={icon.name}
              data-spec-icon={icon.id}
              className="inline-flex shrink-0"
            >
              {picture}
            </span>
          );
        })}
      </span>
      {icons.map((icon) =>
        reasons[icon.id] ? (
          <span
            key={icon.id}
            data-spec-icon-reason={icon.id}
            className="basis-full text-xs text-muted-foreground"
          >
            shown because {reasons[icon.id]}
          </span>
        ) : null,
      )}
    </span>
  );
}
