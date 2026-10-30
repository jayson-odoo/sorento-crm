# TAG-BRAND-CLASS browser pass (cloud sandbox, 30 Oct 2026)

Stack: backend uvicorn :8000 on the sandbox DB `sorento_browse` (bootstrapped empty schema, every
module enabled, invented seed: brands SORENTO and MOCHA, classes SERENE and DIY in Sorento plus DIY
in Mocha, four demo products, one contact "Dealer Demo A"), frontend `npm run dev` :3000
(`.env.local` not committed), agent-browser 0.27.0 session `tbc`. Signed in as a sandbox super
admin. Contact Tags reached by sidebar clicks (Users & Access > Access > Contact Tags). The contact
was opened from Internal Users (the in-page link on Respond.io Contacts, after the sidebar group
would not expand there).

| # | Check | Screenshot | Result |
| --- | --- | --- | --- |
| 1 | Tag Brands row, "Set on this tag" on: All brands switch on, "Allowed item classes" picker under it reading "All classes"; options No class, SORENTO LITE - DIY, SORENTO SERENE SERIES | 01-tag-brands-row-edit-1280.png | PASS |
| 2 | Picking DIY also ticks No class; Save stores `{"brands": "all", "item_classes": ["__NONE__", "DIY"]}` | 01 | PASS |
| 3 | View mode: All brands, Allowed item classes No class + SORENTO LITE - DIY, no SERENE | 02-tag-brands-row-view-1280.png | PASS |
| 4 | Contact Profile > Brands card: same picker, no per-brand rows; DIY pick ticks No class; Save toasts "Brands saved", column holds `{__NONE__,DIY}` | 03-contact-brands-card-edit-1280.png | PASS |
| 5 | Contact card at 375px: chips wrap, nothing clipped | 04-contact-brands-card-375.png | PASS |
| 6 | Apply tag settings preview: "Allowed item classes: All -> No class, SORENTO LITE - DIY", decided by the tag; Apply writes `{__NONE__,DIY}`, `brand_class_ids` untouched (NULL) | 05-apply-preview-1280.png | PASS |
| 7 | After Apply the Brands card kept showing "All classes" until a reload | - | FOUND, fixed: `useApplyTagSettings` now invalidates `contact-brand-scope`; re-run shows the new classes without a reload |

The chatbot / MCP effect (SERENE hidden) is covered by `tests/test_item_class_scope_paths.py`
(every brand-scoped REST path over X-API-Key + contact_id) and `tests/test_allowed_item_class_scope.py`.
| 8 | Fix round (review S1): tag Brands row, "Set brands" switched off reads "Brands not set", classes stay; Save stores `{"item_classes": ["__NONE__", "DIY"]}` with no `brands` key; 375px layout fine | 06-tag-classes-only-375.png | PASS |
| 9 | Re-check on head 0ca7ed457 (backend restarted on that head): tag view "Brands not set" + classes; tag edit "Set brands" on/off; contact Apply preview "All -> No class, SORENTO LITE - DIY" with no Brands line, card refreshes without a reload, `brand_ids` untouched | - | PASS |
