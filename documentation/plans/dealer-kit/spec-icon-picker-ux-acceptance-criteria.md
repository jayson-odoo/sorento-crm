# UAC: spec icon picker (SPEC-ICON-PICKER-UX)

1. Clicking an icon tile in "Icons for <choice>" marks it selected (check mark + ring); clicking again unselects. Nothing changes on the choice yet.
2. Icons the choice already carries open pre-selected, in their current order.
3. Several icons can be selected; Done saves them to the choice in the order they were selected.
4. Cancel, the X, Escape or clicking outside closes the dialog and the choice's icons are unchanged.
5. Uploading artwork adds it to the grid already selected; it reaches the choice only on Done.
6. The designer's Image dialog "Icons" filter lists exactly the icons the spec picker lists (same library, same kind filter).
7. Saving only Icon order or value icons on a spec succeeds while another spec's products are being re-read; it starts no product re-read ("0 products updated").
8. A save that changes rules while another re-read runs is refused, stores nothing, and the message names the spec being re-read and when it started.
9. After saving Icon order, the Details tab shows the new number, including after a reload within a minute.
