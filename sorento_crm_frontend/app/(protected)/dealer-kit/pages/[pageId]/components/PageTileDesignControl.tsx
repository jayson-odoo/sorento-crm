'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { SearchableSelect } from '@/components/common/SearchableSelect';

import { listTileTemplates } from '../../../services/catalogueService';
import type { PageTileTemplateLink } from '../../../services/dealerKitService';
import { useSetPageTileTemplate } from '../hooks/usePageTileTemplate';

export interface PageTileDesignControlProps {
  pageId: string;
  /** The design in force, or null for the renderer's built-in field list. */
  tileTemplateId: string | null;
  /** Its name, resolved by the backend. */
  tileTemplateName: string | null;
  /** Told the moment it is saved, so the canvas repaints its tiles. */
  onApplied?: (link: PageTileTemplateLink) => void;
}

/**
 * The design this brochure's tiles use.
 *
 * ONE control, for the document. The only way to choose a design used to be per
 * collection block, and a brochure seeded from the printed A3 flyer is 341
 * blocks that bind none: picking one changed a single row out of 341, so the
 * honest reading of it was that choosing a tile design did nothing at all.
 *
 * A block may still name its own, which wins. This is the default behind them.
 */
export function PageTileDesignControl({
  pageId,
  tileTemplateId,
  tileTemplateName,
  onApplied,
}: PageTileDesignControlProps) {
  // Saved state, not a draft: it moves only once the backend confirms, so a
  // failed save cannot leave the control looking as though it worked.
  const [link, setLink] = useState<PageTileTemplateLink>({
    tileTemplateId,
    tileTemplateName,
  });
  useEffect(() => {
    setLink({ tileTemplateId, tileTemplateName });
  }, [tileTemplateId, tileTemplateName]);

  const { data: templates = [] } = useQuery({
    queryKey: ['dealer-kit', 'tile-templates'],
    queryFn: listTileTemplates,
  });
  const { mutate, isPending } = useSetPageTileTemplate(pageId);

  const handleChange = (value: string) => {
    const next = value || null;
    // Re-picking what is already applied is not a change worth a write.
    if (next === link.tileTemplateId) return;
    mutate(next, {
      onSuccess: (saved) => {
        setLink(saved);
        onApplied?.(saved);
      },
    });
  };

  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="shrink-0 text-xs text-muted-foreground">Tiles look like</span>
      <SearchableSelect
        id="dk-page-tile-design"
        size="sm"
        value={link.tileTemplateId ?? ''}
        onChange={handleChange}
        options={templates.map((template) => ({
          value: template.id,
          label: template.name,
        }))}
        // Falls back to the renderer's built-in fields, which is a finished
        // state rather than a missing answer - so the placeholder says what the
        // reader gets, not "choose something".
        placeholder="Standard tile"
        selectedOption={
          link.tileTemplateId
            ? {
                value: link.tileTemplateId,
                label: link.tileTemplateName?.trim() || 'Tile design',
              }
            : undefined
        }
        clearable
        disabled={isPending}
        triggerClassName="w-48"
      />
    </div>
  );
}
