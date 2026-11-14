# PRICETAG-DESIGNER-FEEDBACK mock: element to component

Base path `sorento_crm_frontend/`; tag-templates = `app/(protected)/dealer-kit/tag-templates/components`.

| Mocked element | Reuses |
| --- | --- |
| Description toolbar (B/I/U/S, headings, align, lists, undo/redo) | `components/ui/rich-text-editor.tsx` (Toggle toolbar buttons) |
| NEW font dropdown + pt size field | added to `components/ui/rich-text-editor.tsx` toolbar; options via `SearchableSelect` |
| Selected-text sample, indented lines | rich-text-editor content area (`InlineTextEditor.tsx` in tag-templates) |
| Accessories box canvas and cards | tag-templates `AccessoryEditOverlay.tsx` |
| Right-click menu (Change photo, Reset to product photo) | `components/ui/context-menu.tsx` |
| "Choose an image" dialog, tabs Product photos / Asset library, Upload artwork | tag-templates `AssetPickerDialog.tsx` (`allowProductPhotos`, `onPick`) |
| Multi-select dialog, "3 selected", Done, Cancel | `AssetPickerDialog.tsx` select mode (`selectedIds`, `onDone`); count text is new footer copy |
| Columns / Rows selects (Auto/1/2/3/4) | `SearchableSelect` + `COLUMN_OPTIONS` in tag-templates `InspectorPanel.tsx` (~2315, ~2808); replaces "One column or row" placeholder; Rows is a new twin select |
| Spec icons box inspector and icon tiles | tag-templates `InspectorPanel.tsx` feature icons section |
| Icon visibility checklist | checkbox rows in `InspectorPanel.tsx` (shadcn `Checkbox`, `components/ui/checkbox.tsx`) |
| Buttons (Cancel outline, Done filled) | `components/ui/button.tsx` |
