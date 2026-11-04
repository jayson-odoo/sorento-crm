# UAC: quotation perf hotfix (3 Nov)

1. Opening the spec sheet tab loads thumbnail images, not originals; only visible page thumbnails
   render.
2. Export PDF still produces the same pages, with images at no more than ~200 dpi for the page.
3. The customer sign page shows the same columns and pictures as before; hidden photo/drawing
   columns fetch no images; at most 60 pictures inline; a failed image is not retried for ~10 min;
   switching browser tabs does not refetch the page.
