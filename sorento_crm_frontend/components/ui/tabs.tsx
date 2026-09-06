'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { cva, type VariantProps } from 'class-variance-authority';
import { Tabs as TabsPrimitive } from 'radix-ui';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useHorizontalOverflow } from '@/hooks/use-horizontal-overflow';
import { PRESSED_CLASS } from '@/components/ui/primitive-classes';
import { Button } from '@/components/ui/button';
import { useReducedMotion } from '@/lib/motion';

// Variants for TabsList
const tabsListVariants = cva(
  // The list owns its scroller. Without one, Settings hid 7 of its 10 tabs at
  // 375 and the Product create strip overlapped five pills; with `max-w-full` +
  // `min-w-0` the strip scrolls instead of widening the page. The scrollbar is
  // hidden because it would sit on top of the tab labels, so a mask on
  // whichever edge(s) still have more to show (`data-fade-start` /
  // `data-fade-end`, from `useHorizontalOverflow`) is what says so instead -
  // one mask, one, two or the two combined stops depending on which edges fade.
  'flex items-center shrink-0 min-w-0 max-w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ' +
    'data-[fade-start=true]:data-[fade-end=false]:[mask-image:linear-gradient(to_right,transparent,black_24px)] ' +
    'data-[fade-end=true]:data-[fade-start=false]:[mask-image:linear-gradient(to_right,black_calc(100%-24px),transparent)] ' +
    'data-[fade-start=true]:data-[fade-end=true]:[mask-image:linear-gradient(to_right,transparent,black_24px,black_calc(100%-24px),transparent)]',
  {
  variants: {
    variant: {
      default: 'bg-muted p-1',
      button: '',
      line: 'border-b border-border',
    },
    shape: {
      default: '',
      pill: '',
    },
    size: {
      lg: 'gap-2.5',
      md: 'gap-2',
      sm: 'gap-1.5',
      xs: 'gap-1',
    },
  },
  compoundVariants: [
    { variant: 'default', size: 'lg', className: 'p-1.5 gap-2.5' },
    { variant: 'default', size: 'md', className: 'p-1 gap-2' },
    { variant: 'default', size: 'sm', className: 'p-1 gap-1.5' },
    { variant: 'default', size: 'xs', className: 'p-1 gap-1' },

    {
      variant: 'default',
      shape: 'default',
      size: 'lg',
      className: 'rounded-lg',
    },
    {
      variant: 'default',
      shape: 'default',
      size: 'md',
      className: 'rounded-lg',
    },
    {
      variant: 'default',
      shape: 'default',
      size: 'sm',
      className: 'rounded-md',
    },
    {
      variant: 'default',
      shape: 'default',
      size: 'xs',
      className: 'rounded-md',
    },

    { variant: 'line', size: 'lg', className: 'gap-9' },
    { variant: 'line', size: 'md', className: 'gap-8' },
    { variant: 'line', size: 'sm', className: 'gap-4' },
    { variant: 'line', size: 'xs', className: 'gap-4' },

    {
      variant: 'default',
      shape: 'pill',
      className: 'rounded-full [&_[role=tab]]:rounded-full',
    },
    {
      variant: 'button',
      shape: 'pill',
      className: 'rounded-full [&_[role=tab]]:rounded-full',
    },
  ],
    defaultVariants: {
      variant: 'line',
      size: 'md',
    },
  },
);

// Variants for TabsTrigger
const tabsTriggerVariants = cva(
  PRESSED_CLASS +
    ' shrink-0 cursor-pointer whitespace-nowrap inline-flex justify-center items-center font-medium ring-offset-background focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:shrink-0 [&_svg]:text-muted-foreground [&:hover_svg]:text-primary [&[data-state=active]_svg]:text-primary',
  {
    variants: {
      variant: {
        default:
          'text-muted-foreground data-[state=active]:bg-popover hover:text-foreground data-[state=active]:text-foreground data-[state=active]:shadow-xs data-[state=active]:shadow-black/5',
        button:
          'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-lg text-accent-foreground hover:text-foreground data-[state=active]:bg-accent data-[state=active]:text-foreground',
        line: 'border-b-2 text-muted-foreground border-transparent data-[state=active]:border-primary hover:text-primary data-[state=active]:text-primary data-[state=active]:border-primary data-[state=active]:text-primary',
      },
      size: {
        lg: 'gap-2.5 [&_svg]:size-5 text-sm',
        md: 'gap-2 [&_svg]:size-4 text-sm',
        sm: 'gap-1.5 [&_svg]:size-3.5 text-xs',
        xs: 'gap-1 [&_svg]:size-3.5 text-xs',
      },
    },
    compoundVariants: [
      { variant: 'default', size: 'lg', className: 'py-2.5 px-4 rounded-md' },
      { variant: 'default', size: 'md', className: 'py-1.5 px-3 rounded-md' },
      { variant: 'default', size: 'sm', className: 'py-1.5 px-2.5 rounded-sm' },
      { variant: 'default', size: 'xs', className: 'py-1 px-2 rounded-sm' },

      { variant: 'button', size: 'lg', className: 'py-3 px-4 rounded-lg' },
      { variant: 'button', size: 'md', className: 'py-2.5 px-3 rounded-lg' },
      { variant: 'button', size: 'sm', className: 'py-2 px-2.5 rounded-md' },
      { variant: 'button', size: 'xs', className: 'py-1.5 px-2 rounded-md' },

      { variant: 'line', size: 'lg', className: 'py-3' },
      { variant: 'line', size: 'md', className: 'py-2.5' },
      { variant: 'line', size: 'sm', className: 'py-2' },
      { variant: 'line', size: 'xs', className: 'py-1.5' },
    ],
    defaultVariants: {
      variant: 'line',
      size: 'md',
    },
  },
);

// Variants for TabsContent
const tabsContentVariants = cva(
  'mt-2.5 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  {
    variants: {
      variant: {
        default: '',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

// The edge chevron's own box stays the design's 28px circle (`size-7`); this
// widens only the INTERACTIVE box to the DESIGN-LANGUAGE 44px minimum
// (`-inset-2` = 8px each side, 28 + 8 + 8 = 44) via an invisible `::before`.
// `COARSE_HIT_TARGET_CLASS` (baked into `Button size="icon"`) only fires
// under `pointer-coarse` - deliberately, so a mouse's precision is not
// spent on every icon button in a dense cluster (documented on that class).
// The chevron is not that case: it is a single control at a fading edge,
// not packed against neighbours, so it gets the wider box for a mouse too;
// the extra reach lands inside the zone the fade mask already de-emphasises.
// Evidence: documentation/evidence/tabs-overflow-5sep/README.md check 5b.
const CHEVRON_HIT_AREA_CLASS = "before:absolute before:-inset-2 before:content-['']";

// Context
type TabsContextType = {
  variant?: 'default' | 'button' | 'line';
  size?: 'lg' | 'sm' | 'xs' | 'md';
};
const TabsContext = React.createContext<TabsContextType>({
  variant: 'line',
  size: 'md',
});

// Components
function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn('', className)} {...props} />;
}

function TabsList({
  className,
  variant = 'line',
  shape = 'default',
  size = 'md',
  ref: callerRef,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> & VariantProps<typeof tabsListVariants>) {
  const { ref: scrollerRef, isFadingStart, isFadingEnd } = useHorizontalOverflow<HTMLDivElement>();
  const prefersReducedMotion = useReducedMotion();

  // The list needs its own ref to measure the overflow, but it is not entitled to
  // the caller's: placing ours after {...props} silently dropped one.
  const mergedRef = React.useCallback(
    (node: HTMLDivElement | null) => {
      scrollerRef.current = node;
      if (typeof callerRef === 'function') callerRef(node);
      else if (callerRef) callerRef.current = node;
    },
    [scrollerRef, callerRef],
  );

  // A trackpad and shift+wheel already move an overflowing strip sideways -
  // the browser reads those as a horizontal delta on its own. A plain
  // vertical wheel (any ordinary mouse) does not, and left the strip exactly
  // where it last scrolled with no way for that user to move it (prod
  // defect, 5 Sep). `{ passive: false }` is required for `preventDefault` to
  // take effect, and React's own `onWheel` cannot be marked passive, hence a
  // manual listener. Anything already read as horizontal, or a list that
  // fits, is left alone so the page keeps scrolling normally.
  React.useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (el.scrollWidth - el.clientWidth <= 1) return;
      // `deltaMode` 1 (DOM_DELTA_LINE) reports a handful of lines rather
      // than pixels - some Windows mouse-wheel settings and Firefox use it
      // - so a raw deltaY of e.g. 3 barely moves the strip. 16 matches the
      // browser's own line-height assumption for a native vertical scroll.
      const scale = event.deltaMode === 1 ? 16 : 1;
      const deltaY = event.deltaY * scale;
      const deltaX = event.deltaX * scale;
      if (Math.abs(deltaY) <= Math.abs(deltaX)) return;
      el.scrollLeft += deltaY;
      event.preventDefault();
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [scrollerRef]);

  // Keeping the active/focused tab in view: Radix computes `data-state` on
  // `TabsPrimitive.Trigger` itself from its own (unexported) context, and a
  // context change re-renders that trigger directly rather than this
  // wrapper - a plain effect here would never re-fire on a later value
  // change. A `MutationObserver` on the list is the one place that reliably
  // sees every `data-state` flip, mount included, without TabsList having to
  // duplicate Radix's own active-value tracking.
  React.useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const revealActiveTab = () => {
      const active = el.querySelector<HTMLElement>('[role="tab"][data-state="active"]');
      active?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
    };
    revealActiveTab();
    const observer = new MutationObserver(revealActiveTab);
    observer.observe(el, { attributes: true, attributeFilter: ['data-state'], subtree: true });
    return () => observer.disconnect();
  }, [scrollerRef]);

  const scrollByChevron = (direction: 1 | -1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
  };

  return (
    <TabsContext.Provider value={{ variant: variant || 'line', size: size || 'md' }}>
      <div className="relative">
        {isFadingStart && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Scroll tabs left"
            onClick={() => scrollByChevron(-1)}
            className={cn(
              'absolute left-0.5 top-1/2 z-10 size-7 -translate-y-1/2 rounded-full',
              CHEVRON_HIT_AREA_CLASS,
            )}
          >
            <ChevronLeft />
          </Button>
        )}
        <TabsPrimitive.List
          data-slot="tabs-list"
          data-fade-start={isFadingStart}
          data-fade-end={isFadingEnd}
          className={cn(tabsListVariants({ variant, shape, size }), className)}
          {...props}
          ref={mergedRef}
        />
        {isFadingEnd && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Scroll tabs right"
            onClick={() => scrollByChevron(1)}
            className={cn(
              'absolute right-0.5 top-1/2 z-10 size-7 -translate-y-1/2 rounded-full',
              CHEVRON_HIT_AREA_CLASS,
            )}
          >
            <ChevronRight />
          </Button>
        )}
      </div>
    </TabsContext.Provider>
  );
}

function TabsTrigger({ className, onFocus, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  const { variant, size } = React.useContext(TabsContext);

  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(tabsTriggerVariants({ variant, size }), className)}
      // Keyboard/roving-focus navigation can move the focused tab off-screen
      // on a long strip; this keeps it visible the moment focus lands,
      // independent of the list's own MutationObserver (which only fires on
      // a `data-state` change, i.e. once the tab is also selected).
      onFocus={(event) => {
        onFocus?.(event);
        event.currentTarget.scrollIntoView({ inline: 'nearest', block: 'nearest' });
      }}
      {...props}
    />
  );
}

function TabsContent({
  className,
  variant,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content> & VariantProps<typeof tabsContentVariants>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn(tabsContentVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Tabs, TabsContent, TabsList, TabsTrigger };
