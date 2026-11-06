# PLAN: per-selection formatting in tag designer text layers (DESIGNER-RICH-TEXT, 6 Nov)

Status: Plan. Small fix track candidate (no migration, no auth/RBAC, no new ingest); the diff size
decides it once measured.

Owner ask (6 Nov ~10:30): a Text layer's Content can only be styled as a whole. Selecting
`{{product.code}}` and pressing Cmd+B bolds the whole box. He wants bold / italic / underline /
strike / colour per selection inside one text box, with Insert field still working and tokens kept
atomic.

Owner bug folded in (6 Nov, same canvas code): right-click on a multi-selection replaces it with the
frame layer, so Group is never enabled; the context menu shows `Ctrl+` on macOS.

Details follow as the lane is measured.
