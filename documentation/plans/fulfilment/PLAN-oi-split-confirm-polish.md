# PLAN: OI-SPLIT-CONFIRM-POLISH

Status: in progress (small fix track: UI polish, no migration, no auth/RBAC change)

Owner feedback (21 Oct 2026) on the guided Confirm dialog, step 1 "Review split":

1. Remove the row drag handle and drag-to-reorder (and the "Moved ... Undo" toast it raised).
2. Rename CHANGE QUANTITY -> BREAKDOWN QTY and CHANGE DATE -> BREAKDOWN DATE. QTY / NEW QTY /
   DELIVERY DATE / NEW DATE stay (they mirror the OI email).
3. The dialog opens clean: no Save/Undo, Next: Confirm enabled, no "Save or undo" warning until a
   real edit. Fix the dirty-on-open cause at the source.
4. Table columns resizable by dragging the header edge, reusing the app's existing pattern.

Tests (red first): no drag handle; renamed headers; opens clean; warning only after an edit;
columns resizable.
