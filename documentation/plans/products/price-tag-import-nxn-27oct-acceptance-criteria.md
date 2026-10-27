# UAC: price tag import, dimension spacing and line order

- AC-1: rows `Floor Trap\n150x150` and `Floor Trap\n150 x 150` for one code are one text; the first row's text is written, nothing skipped.
- AC-2: `x`, `X` and `×` between two numbers, with or without spaces, compare equal.
- AC-3: a row `Floor Trap\n150 x 150\nGunmetal` beside `Floor Trap\n150x150` wins (it contains the other).
- AC-4: two rows printing the same lines in a different order are one text; the first row's text is written.
- AC-5: two rows that differ in a line (Pillar vs Wall) are still skipped as "same code on several rows with different text", and the skipped CSV lists both sheet row numbers and both texts.
