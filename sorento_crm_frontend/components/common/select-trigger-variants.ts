import { cva, type VariantProps } from 'class-variance-authority';

/**
 * Canonical trigger appearance for ALL dropdown-selects in the system.
 *
 * Single source of truth shared by the Radix `SelectTrigger` (`components/ui/select.tsx`,
 * pending removal) and the standard `SearchableSelect` / `SearchableMultiSelect`
 * (`components/common/`). Because both import THIS module, a migrated dropdown is
 * pixel-identical to the Radix Select it replaced - parity is structural, not copied.
 *
 * Doctrine: every dropdown-select must be searchable and use the standard component.
 * See `documentation/reference/ADR-PRODUCT-STANDARDS.md`.
 */
export const selectTriggerVariants = cva(
  `
    flex bg-background w-full items-center justify-between outline-none border border-input shadow-xs shadow-black/5 transition-shadow
    text-foreground data-placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px]
    focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1
    aria-invalid:border-destructive/60 aria-invalid:ring-destructive/10 dark:aria-invalid:border-destructive dark:aria-invalid:ring-destructive/20
    [[data-invalid=true]_&]:border-destructive/60 [[data-invalid=true]_&]:ring-destructive/10  dark:[[data-invalid=true]_&]:border-destructive dark:[[data-invalid=true]_&]:ring-destructive/20
  `,
  {
    variants: {
      size: {
        sm: 'h-7 px-2.5 text-xs gap-1 rounded-md',
        md: 'h-8.5 px-3 text-[0.8125rem] leading-(--text-sm--line-height) gap-1 rounded-md',
        lg: 'h-10 px-4 text-sm gap-1.5 rounded-md',
      },
    },
    defaultVariants: {
      size: 'md',
    },
  },
);

export type SelectTriggerSize = NonNullable<VariantProps<typeof selectTriggerVariants>['size']>;
