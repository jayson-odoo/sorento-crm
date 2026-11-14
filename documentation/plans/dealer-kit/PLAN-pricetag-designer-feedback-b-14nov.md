# PLAN: price tag designer feedback B (14 Nov)

Status: Build slice B (size L, LEAD pattern). Items 1, 3, 5-8. Phase B1 (files #2349 does not touch): item 6 picker, item 7 layout, item 1 editor + layout + sanitiser. Phase B2 after #2349 merges: item 3 photo (migration + accessory_service), item 5, item 8, inspector and canvas wiring. Slice 1 = PR #2414.

Owner feedback list (9 items) lives in the lane brief. Discovery (file:line causes), the behaviour
card and the UAC land here before any code.

## Owner answers (14 Nov 16:25 mock v1 "ok"; 16:45 answers)

- Q1 item 3: the accessory photo is saved per main product + accessory link (one nullable column, like product_accessories.image_id).
- Q2 item 8 (owner 16:53 "ok b"): spec icon show/hide is saved per product on each tag; other products on the same template are unaffected.
- Q3 item 1: the inspector font list (uploaded fonts included) and sizes in pt.
- Q4 items 5, 7 (CHANGED 16:45): never hide an item that does not fit. No silent drop: the box grows (more rows); if it reaches the page edge, a visible warning on the canvas names what does not fit. Shrinking stops at a minimum readable size (no shrink-until-invisible). Applies to the Accessories box and the Spec icons box.
- Q5 item 6: picking several images makes one box per image.

## Discovery (main @ 94f041b8; file:line causes)

Overlap: #2349 (SPEC-SHEET-PARITY-B2, open draft) edits TagCanvasEditor, InlineTextEditor,
InspectorPanel, KonvaTagLayer, rich-text.ts, accessory-card.ts. This lane rebases on it after it
merges and does not touch its table, font upload or toolbar work.

### Items 1, 2, 4 (text)

# Discovery: price tag description text (read-only). Paths rel. to sorento_crm_frontend/ unless noted.
TT = app/(protected)/dealer-kit/tag-templates/components

## Item 2 - leading spaces lost
(a) Editor = TipTap (StarterKit + TextStyle/Color/TextAlign [+MergeFieldNode]) in components/ui/rich-text-editor.tsx (RichTextEditor, :660-718 extensions, :803 useEditor).
 Description editor with Insert field: master-data-management/products/[id]/components/ProductCombosSection.tsx:257-289 (combo, mergeFields, toolbar full) and ProductSpecificationsTab.tsx:307-318 (price_tag_description). Designer's own boxes: TT/InspectorPanel.tsx:840 (toolbar "inline") and TT/InlineTextEditor.tsx:201 (toolbar "none").
 Serialisation: onUpdate -> fromEditor(normaliseEditorHtml(e.getHTML())) (rich-text-editor.tsx:840-843). Spaces are NOT touched on the way out (normaliseEditorHtml :134-155 only rewrites style attrs; backend app/utils/tag_rich_text.py handle_data :142-147 escapes text as-is; plain mode returns value untouched :206-207). Designer boxes store via lib/dealer-kit/layer-content.ts:20-44 (unformatted -> plain text via textContent, spaces kept).
 LOAD (editor side, "after refresh spaces gone in editor"): value -> toEditorHtml (lib/dealer-kit/rich-text.ts:271-278) -> `<p>   L580..</p>` -> content: toEditor(value) (rich-text-editor.tsx:807, resync :857). useEditor has NO editorProps/parseOptions preserveWhitespace (grep: none in file), so ProseMirror's DOMParser default strips leading/collapses whitespace in `<p>`. Root cause (inferred from ProseMirror/TipTap default, not run): add parseOptions:{preserveWhitespace:'full'} to useEditor at :803 (and `white-space: pre-wrap` is only set for bare variant :816; non-bare 'prose' class :818 has none, though ProseMirror CSS adds pre-wrap while typing). After first edit on reload the stripped HTML is what gets saved.
 Minor: ProductCombosSection.tsx:233 draft.trim() only trims whole string ends (first line of plain text), not rich.
(b) KonvaTagLayer.tsx:272 parseRichText when isRich; RichTextContent :732-805 draws one <Text> per run at run.x_mm from lib/dealer-kit/text-layout.ts richLayerLines (:297-). parseRichText (rich-text.ts:111-124 collectRuns, pushRun :102-108) KEEPS spaces (only \r?\n -> ' ').
 ROOT CAUSE of dropped indent = text-layout.ts richLayerLines: tokenizer TOKEN :295 splits spaces as separate tokens; space tokens go to `space` buffer (:351-353, reset on newline :349); the buffer is emitted only `if (line.length > 0)` (:388-391) and spaceWidth forced 0 when line empty (:374). So leading whitespace of every line/paragraph is discarded (intentional - see tests lib/dealer-kit/text-lines.no-measure.test.ts:48 "no leading space"). Also wrapped continuation lines trimStart in plain path (wrapTextLines :172,:176) - plain hard lines (:184) keep spaces, but a plain description with indent only reaches this when not rich. Print page uses same function (same fix covers both).
 Fix sketch: seed first group's `space` into the line when at line start for a hard-line start (not wrap continuation), count its width in lineWidth, and have x start after it.

## Item 4 - Insert field "in preview mode"
 There is NO Preview toggle in template editor/request designer. "Preview" = eye chip per product block (TagCanvasEditor.tsx PreviewEyeButton :368, state `previews` :755, openBlockPreview :1326, comboPreview :799) which makes dataOf() return real data. Request designer modes are only 'design'|'arrange' (RequestTagDesigner.tsx:259); it always has bound data.
 Insert field button: TT/InspectorPanel.tsx:815-826 gated ONLY on `onInsertField` prop (always passed, TagCanvasEditor.tsx:5715). Not disabled. No toolbar button exists (CanvasToolbar none). Dialog TagCanvasEditor.tsx:5852-5870; onDone: if contentEditor() (:4283, Inspector rich editor ref) insertMergeFieldText else writeSelectedContent(content) (:5864-5866) which REPLACES the content.
 Candidate causes while previewing/with data:
  1. Description-bound text layer (slot combo_description/price_tag_description, no override): InspectorPanel.tsx:772-774 descriptionBound -> :829-835 read-only <textarea> instead of RichTextEditor, so no TipTap editor to insert at (contentEditorRef destroyed/null) -> button writes whole-layer override (:5866) / dialog opened with selectedContent (:5856); looks like "can't insert".
  2. Double-click inline edit while data resolves: TagCanvasEditor.tsx:4313-4318 editingIsDescription and :4344-4351 editingResolvedValue (sole-token layer with data -> value) make InlineTextEditor readOnly plain textarea (:5287, rich=false :5292); and the in-place rich editor is toolbar="none" (InlineTextEditor.tsx:202) so it never has Insert field at all; Insert field is Inspector-only.
  3. Dialog preview line only: InsertFieldDialog.tsx:141,243 ("(preview a product to see values)").
 Not found: any `disabled`/hidden gating on previews for Insert field itself. Needs repro to say which one the user hit; most likely #1 or #2.

## Item 1 - per-word font
 Run/mark type: lib/dealer-kit/rich-text.ts:14-23 RichRun = {text,bold,italic,underline,strike,code,color,highlight}. NO fontFamily/fontSize. Parser marksFor :72-88 reads strong/em/u/s/code and span color/background-color only. runFace (text-layout.ts:271-283) states "Family and base size are never taken from the description"; size only from block sizeFactor (h1 1.4,h2 1.2,h3 1.1; rich-text.ts:47).
 Editor: TextStyle+Color+BackgroundColor only (rich-text-editor.tsx:35,702-716); no FontFamily/FontSize ext. Toolbars: full Toolbar (:~360-515: bold/italic/etc, colours, H1-H3 :418-436, lists, link, undo) and InlineToolbar (:369-406: B/I/U/S, colour). Paste strips styles (stripPastedStyles :158-174); the TextStyle parseHTML drops spans without colour (:703-713). Backend allow-list tag_rich_text.py (style props :32,:58) would also need font-family/size allowed. Font family/size/weight exist only element-level: InspectorPanel TypographyControls (:~2990; fontFamily/fontSize props, TextLayerProps) and used by textFace(props).
 To implement: extend RichRun + marksFor + sameMarks (:90-100) + runFace; TipTap FontFamily/FontSize extensions + toolbar; backend allow-list; widths measured per run already (richLayerLines faces per run :321).

## Open work markers
 grep for "SPEC-SHEET-PARITY" and "#2349": no hits anywhere in repo (code, md, git log all branches). Only existing: PS-SPEC-SHEET comment TagCanvasEditor.tsx:5858; git log -5 on these dirs: 42f418bd (#2330), 9e9731b1 (#2321); on text-layout.ts: 2cb4c734 (#2359, MAIN-RED-TAGSHEET: rich text keeps word spaces when it cannot measure - touches richLayerLines, relevant to item 2). Branches: main, claude/pricetag-designer-feedback-4unbgy.

### Item 9 (crop)

# Bug 9 discovery: image crop blank / shaking (read-only)
Base: sorento_crm_frontend/. C = app/(protected)/dealer-kit/tag-templates/components/. LIB = lib/dealer-kit/image-crop.ts

## Implementation map
- Model: layer.props.cropRect = {x,y,width,height} NORMALISED 0-1 vs natural source (LIB:1-21). Absent = full. Units are consistent: cropPixels (LIB:114) -> natural px for Konva `crop`; fittedCropDraw (LIB:138) -> box px. Units look correct; no wrong-unit bug found.
- Render (committed): C/KonvaTagLayer.tsx ImageContent 555-655: crop=cropPixels (610), draw=fittedCropDraw (611), <KonvaImage crop x y width height> (616-623); cover wraps in clipFunc (642).
- Crop mode state: C/TagCanvasEditor.tsx 2317-2518 (cropEditingLayerId, cropDraft, cropDragRef, own useHtmlImage at 2347, layoutForCropRect 2364, enter 2377, commit 2386, drag fns 2404-2506).
- Overlay: TagCanvasEditor.tsx 4987-5075: Group at layer x/y/rotation; dim full-source KonvaImage, bright copy clipped to window, Rect "crop-window" (pan) + 8 Rect handles, all draggable, onDragMove=handleCropDragMove (setCropDraft every move).
- Real layer hidden in crop mode via opacity={0}: main copy 4694, ghost copy 4652. Transformer: enabledAnchors=[] in crop mode (4867) but node still attached.
- Commit: Enter (3727), Stage mousedown on non-crop node (3256-3259) -> commitCrop -> updateLayerProps(id,{cropRect:draft}) (2393, def 986).
- Spec sheet designer: project-sales/.../spec-sheet/[sheetId]/components/ReaderPage.tsx:497 renders the SAME TagCanvasEditor (dynamic import 135; EmbeddedController types in SpecSheetReader.tsx:38, ReaderInspector.tsx:11). So identical crop path, same bug. Price tag template editor: tag-templates/[id]/page.tsx and RequestTagDesigner.tsx also use it. Print path: app/(public)/c/print/tag-sheet/.../TagSheetRenderer.tsx uses cropWindowStyle (LIB:210). Inspector "Reset crop": InspectorPanel.tsx:1409-1415.

## (a) Blank image plausible causes
1. Layer hidden while overlay depends on a SECOND image load. 4694/4652 set opacity 0 as soon as crop mode starts, but overlay renders only if `cropEditingLayer && cropImage && cropLayout && cropDraft` (4987). cropImage comes from a separate useHtmlImage (2347) keyed by cropImageUrl (2344-2346), which calls layerDisplay(layer, dataOf, assetUrls) WITHOUT the 4th arg library.featureIcons that displayFor passes (1940). If url is undefined/differs (library/feature-icon, bound/preview image) or the extra fetch fails (useHtmlImage.ts:48 onerror -> null, no retry; signed URL), the image is invisible for the whole crop session = "image won't show".
2. Stale opacity after commit: commitCrop clears id; opacity prop flips 0 -> undefined (4694, KonvaTagLayer.tsx:159/220 passes `opacity={opacity}` to Group). react-konva must DELETE the attr on undefined; if the installed react-konva/Konva leaves the node at 0 (prop-diff of an explicitly-undefined value), the committed image stays invisible. Could not verify (node_modules absent). Cheap fix: pass 1 not undefined (and same for ghost 0.3).
3. useHtmlImage (useHtmlImage.ts:34-54) does not clear `image` when url changes and has no key; ImageContent shows a grey "Fetching image" placeholder (KonvaTagLayer.tsx:580-596) if image 0x0. After commit nothing re-fetches, so not a reload bug per se.
4. Degenerate crop: clampCropRect (LIB:31) guarantees >=2% and inside [0,1], so crop can't exceed natural size or be zero from drag; a stored cropRect from before a replace-image is dropped (TagCanvasEditor.tsx:3933-3935), so stale-crop-on-new-image is handled. Very thin crop (2%) of a large image yields extreme zoom; fittedCropDraw (LIB:152-156) can then make drawW/H huge under cover (looks blank/solid).
5. Commit gets lost: KonvaTagLayer.handleMouseDown (KonvaTagLayer.tsx:166-179) does e.cancelBubble=true and the hidden (opacity 0) layer stays listening (4649/4690 listening not gated on crop), so a click over the image never reaches the Stage handler (3256) that commits; also drag-start on it drags the real layer (draggable at 4648/4689 not gated on crop mode).

## (b) Shaking causes
1. Window auto-refit each frame (main cause). Every onDragMove -> setCropDraft (2477) -> whole 5.9k-line TagCanvasEditor re-renders. cropLayout (2375) = cropOverlayLayout, where window = fittedCropDraw re-fits the CROPPED region into the layer box (LIB:152-158) and source scale = window/crop (LIB:184-185). So resizing a handle changes the overall scale of the whole photo on every mousemove (shrinking crop = zoom in). Meanwhile cropRectFromEvent (2412-2434) normalises by the BASE layout scale (2423, source.width of the start rect), so pointer distance != on-screen movement; the handle is then forced to the new window anchor (positionCropHandle 2458-2467), not under the cursor -> handle and image jump/zoom continuously = "shaking". A standard crop keeps the picture fixed and moves only the frame.
2. Drag-fight: handler writes node position (2463) inside dragmove while Konva also sets it from pointer and react-konva re-applies x/y props (hx/hy 5058-5059; window.x/y 5022-5023) from the re-render; Konva-set value is read back at 2429-2430 so it is stable numerically but the node visually snaps between pointer pos and window anchor. Pan (crop-window Rect, anchor null -> fallback {fx:0,fy:0} at 2473) resets rect to window top-left every tick.
3. Pan direction inverted: panCropRect adds +dx to crop.x (LIB:106-107); source.x = window.x - crop.x*scale (LIB:189) so dragging the window right slides the picture LEFT under a pinned window. Feels "very weird" (frame stays, photo moves opposite).
4. Hidden real layer is still draggable/listening (4648-4649, 4689-4690): dragging on the dimmed area outside the window moves the real layer x/y (handleDragMove) while the overlay Group is positioned from layer.x_mm (4989-4990), so overlay and layer fight/shift -> whole photo moves.
5. Not a re-fetch flicker: useHtmlImage effect depends only on [url] (useHtmlImage.ts:54); no per-render refetch.

## Existing test
TagCanvasEditor.crop.test.tsx (729 lines): Konva mocked; covers entry (374), Enter/click-outside commit (400-500), Esc (503), dim/bright same transform for cover/contain (532-640), handle stranding (644), Reset crop (680). It never tests visual continuity during drag, committed-layer opacity restored, or overlay-vs-layer image URL parity, so bugs 1-3 above are untested.

## Suggested fix directions (not applied)
- Keep window fixed (fit box to full source once at drag start / use base layout for window+source during drag), commit-time refit only.
- Reuse displayFor(layer).imageUrl (with featureIcons) for cropImage; fall back to showing real layer if cropImage missing.
- Gate draggable/listening of the hidden layer on cropEditingLayerId; use opacity 1 not undefined on exit; invert/flip pan sign.

### Items 3, 5, 6, 7, 8

# Discovery: accessories photo / columns / spec icons / image picker
FE = sorento_crm_frontend ; BE = sorento_crm_backend ; TT = FE/app/(protected)/dealer-kit/tag-templates/components

## Item 3 accessory photo resolution
- FE: card "picture" field -> cardFieldValue() FE/lib/dealer-kit/accessory-card.ts:296-297 = item.image?.url ?? item.images?.[0]?.url. Type TagAccessory.image/images FE/lib/dealer-kit/tag-template-types.ts:942-953. No FE-side override; URL arrives in payload.
- BE two kinds of accessory item (BE/app/services/accessory_service.py):
  * library accessory: tag_accessory() :216-244. Pictures = accessory_images rows (_picture_rows :147), legacy accessories.image_attachment_id fallback :223. Per list-row choice: product_accessories.image_id / product_combo_accessories.image_id (models/accessory.py:137,178) picks which of the accessory's own pictures leads (:230-235). Signed via image_of() :129.
  * catalogue product as accessory (item_product_id): tag_product_entry() :247-279 -> gallery_images(db, product, viewer) (BE/app/services/dealer_kit/product_images.py:~145-195), lead = is_primary else first. i.e. PRODUCT ATTACHMENTS, access-gated (_may_see), ranked Product Photos > other > Technical Specs > Combo Image; only image/* and non-deleted.
  * Lists: product_tag_accessories :311, combo_tag_accessories :316, _tag_entries :282.
  * Resign on pin read: tag_data_service.py ~1972-1995 (uses accessory_service.image_of).
- Override: NO price-tag-level / product-level "tag photo" field exists (grep price_tag_photo/tag_photo = 0 hits). Only: (a) product_attachments.is_primary + sort_order (the "primary" photo, API BE/app/api/v1/master_data/product_attachments.py POST "/" :244, PUT, DELETE, GET /product/{id} :361; brochure-images PUT :108 is promotion brochure choice, not tag); (b) main product: image layer source {type:'product_attachment', attachmentId} per LAYER (tag-template-types.ts:88-91; picked in TagCanvasEditor.handleImagePicked :1506-1530); (c) combo cover product_combos.image_attachment_id (_lead_with_cover tag_data_service.py:1440); (d) accessory row image_id (library accessories only).
- Per-product tag photo upload: none dedicated. Closest to extend: product_attachments create (attachment upload via resources then link, is_primary) ; accessory_service._store/add_image :475/:548 (accessory_image type, store_renditions) for library accessories; product_combo_service.upload_image for combo cover. For a product-as-accessory, add e.g. image_id-like override column (product_accessories.item_image_attachment_id) and teach tag_product_entry to honour it (mirrors tag_accessory :230).

## Item 5 Columns
- Prop: AccessoriesLayerProps.columns?: 'auto'|1|2|3|4  FE/lib/dealer-kit/tag-template-types.ts:451-454 (card path only; absent = single column(vertical)/row(horizontal)).
- UI: InspectorPanel.tsx:2315-2336 SearchableSelect aria-label "Columns", placeholder "One column or row" :2322, clearable, COLUMN_OPTIONS :2808-2814; hint "Only N columns fit" :2149-2156. Setting columns on a legacy box synthesises card via cardFromLegacy :2327-2330.
- Layout: cardBoxLayout() FE/lib/dealer-kit/accessory-card.ts:78 (grid branch :164-215): wanted = columns (auto = floor((innerW+gap)/(cardW+gap))); cols=min(total,wanted); scale=max(fitFor(cols), shrinkMin); reduces cols while too wide; cards fill left->right, wrap to rows (x=pad+(i%cols)*(cw+gap), y=top+floor(i/cols)*(ch+gap)); rows hidden beyond maxRows (whole cards dropped). "2" = 2-across grid wrapping to N rows. columns 1 = single column; null = legacy direction. tooSmall() :112-160 fallback.
- Callers: KonvaTagLayer.tsx DesignedAccessoriesContent :1356-1387 (cardBoxLayout), print page + preview same fn.
- NO rows prop. direction vertical/horizontal (InspectorPanel ~2300) governs only the no-columns case.

## Items 7+8 spec/feature icons
- Layer: FeatureIconsLayerProps FE/lib/dealer-kit/tag-template-types.ts:346-355 {iconSize_mm, gap_mm, align, subjectPart, subjectSlot}; NO order/selection prop (per-template `order` retired, contract lines ~120-123).
- Layout: SINGLE packed row. featureIconRow/featureIconFit FE/lib/dealer-kit/feature-icons.ts:140/:161; icons that don't fit width are DROPPED (dropped warning InspectorPanel FeatureIconsInspector :2713-2780, Alert "N of M icons do not fit"). Drawn KonvaTagLayer.tsx FeatureIconsContent :1120-1160 (switch case :415, :1609). Vertically centred. No wrap/rows.
- Selection: none per product/template. Icons are derived: featureIconsFor(specs, icons) feature-icons.ts:36-57 matches product's tag-payload specs `raw` against rules; rules live on SPEC VALUES (registry value_icons, icon_order, conditions) edited in Product Specifications (Values and words grid, AssetPickerDialog select mode). So user chooses icons per spec value globally (not per product/template). To allow per-template/product pick you'd add a layer prop (e.g. hiddenIconIds/ include list) filtered after featureIconsFor, plus BE FeatureIconsLayerPropsDoc (BE/app/schemas/price_tag.py, ~"FeatureIconsLayerPropsDoc") .
- Data: BE tag_data_service.product_specs :281 -> {key,label,value,raw,unit}; icons list GET /api/v1/dealer-kit/feature-icons BE/app/api/v1/dealer_kit/tag_data.py:152 (asset_service.feature_icon_rules + urls_for); FE service listFeatureIcons, useKitLibrary (useTagBindings.ts:214, featureIconsQuery :225, featureIcons memo ~:325); print gets feature_icons via design_media (public/portal_price_tag.py:999,1014). Accessory cards also have a `feature_icons` card element (accessory-card.ts:478-524, cardIconLayout :599) using item.specs.
- Docs: documentation/plans/dealer-kit/pricetag-feature-icons-contract.md; spec-icon-picker-ux-acceptance-criteria.md (UAC 1-6 = multi-select toggle + Done; UAC 6 designer Image dialog Icons filter = same library).

## Item 6 "Choose an image" dialog
- Component: TT/AssetPickerDialog.tsx. Tabs "Product photos"(:~170, hidden if allowProductPhotos=false) / "Asset library". Default mode = single pick: tile click -> onPick({type:'asset'|'product_attachment'}) (:~205, :~262) and closes. Upload: one file (FileDropzone files[0], title "Upload artwork", button "Upload and use" :~330-340), handleUpload :140-166 -> uploadAsset({file,kind,tags}) FE/app/(protected)/dealer-kit/services/assetService.ts:74-93 POST /api/v1/dealer-kit/assets (BE api/v1/dealer_kit/assets.py:83 upload_asset, perm dealer_kit.library.manage; service asset_service). List: listAssets assetService.ts:59 GET same base (?kind,q,limit=100) BE assets.py:66; kind filter LIBRARY_KINDS (All/Badges/Icons/Diagrams/Logos).
- ALREADY has multi-select mode: props selectedIds + onDone (library tiles only, toggle + check, Done, upload joins selection) - used by spec value icon picker (not TagCanvasEditor).
- Users in TagCanvasEditor.tsx: image layer (InspectorPanel :1323-1353 onChooseImage -> handleChooseImage :1499 -> imagePicker{layerId,badge:false}); badge layer (InspectorPanel :1984-2005 onChooseBadge, handleAddBadge :1255-1260, :1503; badge: allowProductPhotos=false, title "Choose a badge", uploadKind badge); dialog render :5824-5833; handleImagePicked :1506-1530 writes layer.props.source or badge.assetId. Icon library "Icons" dialog (libraryKind="icon") :5836-5850 via Feature icons "Manage icons". Product photos tab fed by pickerProductImages :4470-4475 (data.product.images of bound product).
- Dialog does NOT serve accessory card picture elements (those bind to the accessory's own `picture` field).

## git log -8 (dealer-kit/tag-templates + price-tag-requests)
98dbfaef STANDARD-HISTORY-W5 (#2390); 40f421a5 FORMS-LAST-ACTIVITY (#2361); 7ede7cfa LIST-FILTER-MEMORY-4 (#2362); 42f418bd PROJECT-QUOTE-LINE-TOOLS (#2330); 9e9731b1 PRODUCT-COSTING (#2321). (only 5 commits touch these paths with default depth)
Canvas files only: f0fd5814 CERT-TAB-FOLLOWUPS (#2353)
## SPEC-SHEET-PARITY / 2349
No source/doc file mentions; git history only: 4a2d545c docs(user-guides): spec sheet designer parity slice B (#2349); 0cfd7718 SPEC-SHEET-DESIGNER-PARITY B hand test for PR #2349; ea7e8833/d622c3ac/8ad60125/7bdcb147/6ce64993 SPEC-SHEET-PARITY-B2 (v3 spec sheet editor; unrelated to price tag accessories).


## B2 notes from the B1 review (14 Nov)

- Print parity (standing rule "prints exactly as on screen"): `TagSheetRenderer.tsx:328-329` applies a run's family only for `code` and size only when `sizeFactor !== 1`; B2 must apply run fontFamily/fontSize the same way the canvas does through `runFace`.
- Accessory cards scale and shrink text (`accessory-card.ts:659`, `fitCardTextProps` :684); absolute pt run sizes must scale with them in B2.
- Size field applies on each keystroke (one undo step per keystroke); consider applying on blur/Enter in B2 when it is wired into the inspector.
- List marker width uses the first run's face (`text-layout.ts` `widthOf(marker, 0)`); revisit with lists in B2.
