'use client';

import { useCallback, useMemo, useState } from 'react';
import {
  FileText,
  Heading1,
  Image as ImageIcon,
  LayoutGrid,
  Link2Off,
  Monitor,
  Package,
  Printer,
  RotateCcw,
  Smartphone,
  Square,
  Tablet,
  Type,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { BlockInspector } from './BlockInspector';
import { EMPTY_SELECTION, type ProductSelection } from './ProductPickerDialog';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import {
  createCollection,
  listTileTemplates,
  resolveBundle,
  resolveCollection,
  updateCollection,
} from '../services/catalogueService';
import { cn } from '@/lib/utils';
import {
  BREAKPOINT_COLUMNS,
  createLayouts,
  deriveLayout,
  pinBreakpoint,
  rederiveBreakpoint,
  reflowDerivedBreakpoints,
  type BlockPlacementMap,
  type Breakpoint,
} from '@/lib/dealer-kit/deriveLayout';
import {
  DEFAULT_PRINT_PROFILE,
  defaultHideInPrint,
  type Block,
  type BlockProps,
  type BlockType,
  type PageDoc,
  type Section,
} from '@/lib/dealer-kit/types';

import { BuilderCanvas } from './BuilderCanvas';
import { CollapsiblePanel, FocusShell, FocusToggle } from './FocusMode';
import { PaperCanvas } from './PaperCanvas';

/** Desktop / tablet / mobile, plus paper - the one view allowed to draw page breaks. */
type CanvasMode = Breakpoint | 'paper';

const CANVAS_TABS: { value: CanvasMode; label: string; icon: typeof Monitor }[] = [
  { value: 'desktop', label: 'Desktop', icon: Monitor },
  { value: 'tablet', label: 'Tablet', icon: Tablet },
  { value: 'mobile', label: 'Mobile', icon: Smartphone },
  { value: 'paper', label: 'Paper', icon: Printer },
];

const PALETTE: { type: BlockType; label: string; icon: typeof Type }[] = [
  { type: 'heading', label: 'Heading', icon: Heading1 },
  { type: 'text', label: 'Text', icon: Type },
  { type: 'image', label: 'Image', icon: ImageIcon },
  { type: 'collection', label: 'Products', icon: LayoutGrid },
  { type: 'bundle', label: 'Bundle', icon: Package },
  { type: 'artboard', label: 'Artboard', icon: Square },
];

function newBlock(type: BlockType): Block {
  const id = `blk-${Math.random().toString(36).slice(2, 9)}`;
  const hideInPrint = defaultHideInPrint(type);

  switch (type) {
    case 'heading':
      return { id, type, hideInPrint, props: { kind: 'heading', text: 'New heading', scale: '2xl' } };
    case 'text':
      return { id, type, hideInPrint, props: { kind: 'text', text: 'New text block', scale: 'base' } };
    case 'image':
      return { id, type, hideInPrint, props: { kind: 'image', assetId: null, fit: 'cover' } };
    case 'collection':
      return {
        id,
        type,
        hideInPrint,
        props: {
          kind: 'collection',
          collectionId: null,
          tileTemplateId: null,
          columns: { desktop: 4, tablet: 2, mobile: 1 },
        },
      };
    case 'bundle':
      return { id, type, hideInPrint, props: { kind: 'bundle', bundleId: null, tileTemplateId: null } };
    case 'artboard':
      return { id, type, hideInPrint, props: { kind: 'artboard', aspectRatio: 16 / 9, children: [] } };
    default:
      return { id, type: 'spacer', hideInPrint, props: { kind: 'spacer' } };
  }
}

export interface PageEditorProps {
  /** Needed to own a page-scoped collection, which dies with the page (AC-F4). */
  pageId: string;
  doc: PageDoc;
  /**
   * Updater, not a value. Layout measurement can settle several blocks in one
   * tick, and each of those must build on the previous result rather than on
   * whatever `doc` this render captured.
   *
   * `silent` applies a change without marking the document dirty: the editor
   * reflowing a block to fit its own content is not an edit the user made, and
   * showing "Unsaved changes" for it would be a lie.
   */
  onDocChange: (updater: (previous: PageDoc) => PageDoc, options?: { silent?: boolean }) => void;
}

export function PageEditor({ pageId, doc, onDocChange }: PageEditorProps) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<CanvasMode>('desktop');
  const [focus, setFocus] = useState(false);
  /**
   * Side panels folded away.
   *
   * Only meaningful in full screen: outside it the page scrolls anyway, and a
   * collapsed panel would just be a missing control.
   */
  const [hideLeft, setHideLeft] = useState(false);
  const [hideRight, setHideRight] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(
    doc.sections[0]?.id ?? null,
  );
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Block | null>(null);
  /**
   * The picker's working copy, keyed by block id. It is NEVER written into the
   * saved document - the document carries a `collectionId` and nothing else, so
   * that it holds no product list and no prices (AC-G1). The selection itself
   * lives in a page-scoped Collection row on the server.
   */
  const [selections, setSelections] = useState<Record<string, ProductSelection>>({});

  const activeSection = useMemo(
    () => doc.sections.find((section) => section.id === activeSectionId) ?? null,
    [doc.sections, activeSectionId],
  );

  const breakpoint: Breakpoint = mode === 'paper' ? 'desktop' : mode;
  const isDerived = activeSection?.layouts[breakpoint]?.isDerived ?? false;

  const updateSection = useCallback(
    (
      sectionId: string,
      mutate: (section: Section) => Section,
      options?: { silent?: boolean },
    ) => {
      onDocChange(
        (previous) => ({
          ...previous,
          sections: previous.sections.map((section) =>
            section.id === sectionId ? mutate(section) : section,
          ),
        }),
        options,
      );
    },
    [onDocChange],
  );

  const handlePlacementsChange = useCallback(
    (next: BlockPlacementMap, options?: { silent?: boolean }) => {
      if (!activeSection) return;

      updateSection(activeSection.id, (section) => {
        // Editing desktop reflows every breakpoint still following it. Editing a
        // smaller breakpoint pins it, and desktop stops driving it from here on.
        if (breakpoint === 'desktop') {
          return {
            ...section,
            layouts: reflowDerivedBreakpoints({
              ...section.layouts,
              desktop: { blocks: next, isDerived: false },
            }),
          };
        }

        return { ...section, layouts: pinBreakpoint(section.layouts, breakpoint, next) };
      }, options);
    },
    [activeSection, breakpoint, updateSection],
  );

  /**
   * Grow one block so its content is not clipped (AC-C4).
   *
   * Applied against the latest section rather than a captured placement map, so
   * two blocks growing in the same tick cannot overwrite each other. Idempotent:
   * growing to a span the block already has is a no-op, which is what stops the
   * measure-then-grow cycle from oscillating, and it never marks the document
   * dirty on its own - reflowing to fit content is not an edit the user made.
   */
  const handleGrowBlock = useCallback(
    (blockId: string, rowSpan: number) => {
      if (!activeSection) return;

      updateSection(
        activeSection.id,
        (section) => {
          const current = section.layouts[breakpoint].blocks[blockId];
          if (!current || current.rowSpan >= rowSpan) return section;

          return {
            ...section,
            layouts: {
              ...section.layouts,
              [breakpoint]: {
                ...section.layouts[breakpoint],
                blocks: {
                  ...section.layouts[breakpoint].blocks,
                  [blockId]: { ...current, rowSpan },
                },
              },
            },
          };
        },
        { silent: true },
      );
    },
    [activeSection, breakpoint, updateSection],
  );

  const handleAddBlock = useCallback(
    (type: BlockType) => {
      if (!activeSection) return;
      const block = newBlock(type);

      updateSection(activeSection.id, (section) => {
        const desktop = section.layouts.desktop.blocks;
        const nextRow = Object.values(desktop).reduce(
          (lowest, placement) => Math.max(lowest, placement.rowStart + placement.rowSpan - 1),
          0,
        );

        const nextDesktop: BlockPlacementMap = {
          ...desktop,
          [block.id]: { colStart: 1, colSpan: 6, rowStart: nextRow + 1, rowSpan: 3 },
        };

        return {
          ...section,
          blocks: [...section.blocks, block],
          layouts: reflowDerivedBreakpoints({
            ...section.layouts,
            desktop: { blocks: nextDesktop, isDerived: false },
          }),
        };
      });

      setSelectedBlockId(block.id);
    },
    [activeSection, updateSection],
  );

  const handleDeleteBlock = useCallback(
    (block: Block) => {
      if (!activeSection) return;

      updateSection(activeSection.id, (section) => {
        const strip = (blocks: BlockPlacementMap) => {
          const next = { ...blocks };
          delete next[block.id];
          return next;
        };

        return {
          ...section,
          blocks: section.blocks.filter((candidate) => candidate.id !== block.id),
          layouts: {
            desktop: { ...section.layouts.desktop, blocks: strip(section.layouts.desktop.blocks) },
            tablet: { ...section.layouts.tablet, blocks: strip(section.layouts.tablet.blocks) },
            mobile: { ...section.layouts.mobile, blocks: strip(section.layouts.mobile.blocks) },
          },
        };
      });

      setSelectedBlockId(null);
      setPendingDelete(null);
    },
    [activeSection, updateSection],
  );

  const selectedBlock = useMemo(
    () => activeSection?.blocks.find((block) => block.id === selectedBlockId) ?? null,
    [activeSection, selectedBlockId],
  );

  const handleChangeProps = useCallback(
    (next: BlockProps) => {
      if (!activeSection || !selectedBlock) return;
      updateSection(activeSection.id, (section) => ({
        ...section,
        blocks: section.blocks.map((block) =>
          block.id === selectedBlock.id ? { ...block, props: next } : block,
        ),
      }));
    },
    [activeSection, selectedBlock, updateSection],
  );

  /**
   * Resolution happens on the SERVER, once per bound block.
   *
   * The editor resolves against the Designer's own viewer context, which is why
   * a block can legitimately look different here and on the public page - and
   * why the document itself carries neither tiles nor prices. Resolving in the
   * browser instead would mean a second copy of the rule engine and a preview
   * that could disagree with what gets published.
   */
  const boundBlocks = useMemo(() => {
    const collections: string[] = [];
    const bundles: string[] = [];
    for (const section of doc.sections) {
      for (const block of section.blocks) {
        if (block.props.kind === 'collection' && block.props.collectionId) {
          collections.push(block.props.collectionId);
        }
        if (block.props.kind === 'bundle' && block.props.bundleId) {
          bundles.push(block.props.bundleId);
        }
      }
    }
    return {
      collections: Array.from(new Set(collections)),
      bundles: Array.from(new Set(bundles)),
    };
  }, [doc.sections]);

  const { data: tileTemplates = [] } = useQuery({
    queryKey: ['dealer-kit', 'tile-templates'],
    queryFn: listTileTemplates,
  });

  const collectionQueries = useQueries({
    queries: boundBlocks.collections.map((id) => ({
      queryKey: ['dealer-kit', 'resolve-collection', id],
      queryFn: () => resolveCollection(id),
    })),
  });

  const bundleQueries = useQueries({
    queries: boundBlocks.bundles.map((id) => ({
      queryKey: ['dealer-kit', 'resolve-bundle', id],
      queryFn: () => resolveBundle(id),
    })),
  });

  const resolveBlock = useCallback(
    (block: Block) => {
      // Bound to a local so the narrowing survives into the callbacks below -
      // TypeScript re-widens `block.props` inside a nested closure.
      const props = block.props;

      if (props.kind === 'collection' && props.collectionId) {
        const index = boundBlocks.collections.indexOf(props.collectionId);
        const resolved = collectionQueries[index]?.data;
        if (!resolved) return undefined;
        const template = tileTemplates.find(
          (candidate) => candidate.id === props.tileTemplateId,
        );
        return { tiles: resolved.tiles, tileFields: template?.fields };
      }

      if (props.kind === 'bundle' && props.bundleId) {
        const index = boundBlocks.bundles.indexOf(props.bundleId);
        const resolved = bundleQueries[index]?.data;
        return resolved ? { bundle: resolved } : undefined;
      }

      return undefined;
    },
    [boundBlocks, collectionQueries, bundleQueries, tileTemplates],
  );

  /**
   * Push a product selection to the server.
   *
   * First save creates a page-scoped Collection silently - the Designer never
   * names it and never sees it in the library (AC-F4) - and the block records
   * only its id. The document therefore holds a reference, never a product list
   * and never a price.
   */
  const persistSelection = useCallback(
    async (block: Block, selection: ProductSelection) => {
      if (block.props.kind !== 'collection' || !activeSection) return;
      const existingId = block.props.collectionId;

      const payload = {
        conditions: (selection.conditions as Record<string, unknown> | null) ?? null,
        pinnedProductIds: selection.pinnedProductIds,
        excludedProductIds: selection.excludedProductIds,
      };

      try {
        if (existingId) {
          await updateCollection(existingId, { ...payload, scope: 'page', pageId });
          await queryClient.invalidateQueries({
            queryKey: ['dealer-kit', 'resolve-collection', existingId],
          });
          return;
        }

        const created = await createCollection({ ...payload, scope: 'page', pageId });
        updateSection(activeSection.id, (section) => ({
          ...section,
          blocks: section.blocks.map((candidate) =>
            candidate.id === block.id && candidate.props.kind === 'collection'
              ? { ...candidate, props: { ...candidate.props, collectionId: created.id } }
              : candidate,
          ),
        }));
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Could not save this product selection.',
        );
      }
    },
    [activeSection, pageId, queryClient, updateSection],
  );

  const handleAddSection = useCallback(() => {
    const id = `sec-${Math.random().toString(36).slice(2, 9)}`;
    const section: Section = {
      id,
      name: `Section ${doc.sections.length + 1}`,
      style: { background: 'transparent', paddingY: 'lg' },
      blocks: [],
      layouts: createLayouts({}),
      printMode: 'include',
    };

    onDocChange((previous) => ({ ...previous, sections: [...previous.sections, section] }));
    setActiveSectionId(id);
  }, [doc.sections.length, onDocChange]);

  const handleRederive = useCallback(() => {
    if (!activeSection || breakpoint === 'desktop') return;

    updateSection(activeSection.id, (section) => ({
      ...section,
      layouts: rederiveBreakpoint(section.layouts, breakpoint),
    }));
  }, [activeSection, breakpoint, updateSection]);

  return (
    <FocusShell active={focus} onExit={() => setFocus(false)}>
    <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
      <aside className={cn('w-full shrink-0', focus && hideLeft ? 'lg:w-auto' : 'lg:w-56')}>
        <CollapsiblePanel
          title="Sections and blocks"
          collapsed={focus && hideLeft}
          onToggle={setHideLeft}
          side="start"
          enabled={focus}
        >
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Sections</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 pb-3">
            {doc.sections.length === 0 && (
              <p className="pb-2 text-sm text-muted-foreground">
                No sections yet. Add one to start the page.
              </p>
            )}

            {doc.sections.map((section) => (
              <button
                key={section.id}
                type="button"
                onClick={() => setActiveSectionId(section.id)}
                className={cn(
                  'flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                  section.id === activeSectionId
                    ? 'bg-primary/10 font-medium text-primary'
                    : 'text-muted-foreground hover:bg-muted',
                )}
              >
                <span className="truncate" title={section.name}>
                  {section.name}
                </span>
                {section.printMode === 'breakBefore' && (
                  <Badge variant="outline" appearance="ghost" className="shrink-0 text-[10px]">
                    break
                  </Badge>
                )}
                {section.printMode === 'exclude' && (
                  <Link2Off className="size-3 shrink-0 text-muted-foreground" />
                )}
              </button>
            ))}

            <Button variant="outline" size="sm" className="mt-2" onClick={handleAddSection}>
              Add section
            </Button>
          </CardContent>

          <Separator />

          <CardHeader className="py-3">
            <CardTitle className="text-sm">Blocks</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-1.5 pb-4">
            {PALETTE.map(({ type, label, icon: Icon }) => (
              <Button
                key={type}
                variant="outline"
                size="sm"
                className="h-auto flex-col gap-1 py-2"
                disabled={!activeSection || mode === 'paper'}
                onClick={() => handleAddBlock(type)}
              >
                <Icon className="size-4" />
                <span className="text-[11px]">{label}</span>
              </Button>
            ))}
          </CardContent>
        </Card>
        </CollapsiblePanel>
      </aside>

      <div className="min-w-0 flex-1">
        <Card>
          <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <CardTitle className="truncate text-sm">
                {activeSection?.name ?? 'No section selected'}
              </CardTitle>
              {mode !== 'paper' && (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {BREAKPOINT_COLUMNS[breakpoint]} columns
                  {isDerived && ' · following desktop'}
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {mode !== 'paper' && mode !== 'desktop' && !isDerived && (
                <Button variant="outline" size="sm" onClick={handleRederive}>
                  <RotateCcw className="size-3.5" />
                  Follow desktop again
                </Button>
              )}

              <FocusToggle active={focus} onToggle={setFocus} label="canvas" />

              <Tabs value={mode} onValueChange={(value) => setMode(value as CanvasMode)}>
                <TabsList>
                  {CANVAS_TABS.map(({ value, label, icon: Icon }) => (
                    <TabsTrigger key={value} value={value} className="gap-1.5">
                      <Icon className="size-3.5" />
                      <span className="hidden sm:inline">{label}</span>
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            </div>
          </CardHeader>

          <CardContent className="pb-6">
            {mode === 'paper' ? (
              // A page created by the API, or saved before print settings
              // existed, has no profile of its own but still has to be printable.
              <PaperCanvas
                sections={doc.sections}
                profile={doc.printProfile ?? DEFAULT_PRINT_PROFILE}
              />
            ) : !activeSection ? (
              <div className="rounded-lg border border-dashed border-border p-10 text-center">
                <FileText className="mx-auto size-5 text-muted-foreground" />
                <p className="mt-2 text-sm font-medium text-foreground">No section selected</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Pick a section on the left, or add one.
                </p>
              </div>
            ) : (
              <>
                {isDerived && breakpoint !== 'desktop' && (
                  <div className="mb-3 flex flex-col gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-muted-foreground">
                      This layout follows desktop. Edit it to take manual control of this
                      breakpoint.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      onClick={() =>
                        activeSection &&
                        updateSection(activeSection.id, (section) => ({
                          ...section,
                          layouts: pinBreakpoint(
                            section.layouts,
                            breakpoint,
                            deriveLayout(
                              section.layouts.desktop.blocks,
                              BREAKPOINT_COLUMNS[breakpoint],
                            ),
                          ),
                        }))
                      }
                    >
                      Edit this breakpoint
                    </Button>
                  </div>
                )}

                <BuilderCanvas
                  blocks={activeSection.blocks}
                  placements={activeSection.layouts[breakpoint].blocks}
                  breakpoint={breakpoint}
                  selectedBlockId={selectedBlockId}
                  locked={isDerived && breakpoint !== 'desktop'}
                  onSelectBlock={setSelectedBlockId}
                  onPlacementsChange={handlePlacementsChange}
                  onGrowBlock={handleGrowBlock}
                  resolveBlock={resolveBlock}
                  onDeleteBlock={(blockId) => {
                    const block = activeSection.blocks.find((item) => item.id === blockId);
                    if (block) setPendingDelete(block);
                  }}
                />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <aside className={cn('w-full shrink-0', focus && hideRight ? 'lg:w-auto' : 'lg:w-64')}>
        <CollapsiblePanel
          title="Block settings"
          collapsed={focus && hideRight}
          onToggle={setHideRight}
          side="end"
          enabled={focus}
        >
        <BlockInspector
          block={mode === 'paper' ? null : selectedBlock}
          selection={selectedBlock ? selections[selectedBlock.id] ?? EMPTY_SELECTION : EMPTY_SELECTION}
          onChangeProps={handleChangeProps}
          onChangeSelection={(next) => {
            if (!selectedBlock) return;
            setSelections((current) => ({ ...current, [selectedBlock.id]: next }));
            void persistSelection(selectedBlock, next);
          }}
        />
        </CollapsiblePanel>
      </aside>

      <ConfirmDeleteDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        onDelete={async () => {
          if (pendingDelete) handleDeleteBlock(pendingDelete);
        }}
        successMessage="Block removed"
        title="Confirm delete"
        description={`This removes the ${pendingDelete?.type ?? ''} block from this section. This action cannot be undone.`}
      />
    </div>
    </FocusShell>
  );
}
