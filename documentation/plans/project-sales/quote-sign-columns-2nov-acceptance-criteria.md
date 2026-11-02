# UAC: QUOTE-SIGN-COLUMNS

- AC1. For a scope where at least one line has a product photo, the sign page's column labels,
  in order, equal the quotation PDF's column labels (PRODUCT IMAGE included).
- AC2. For a scope with no photo on any line, the sign page omits the photo column exactly as the
  PDF does.
- AC3. The column list comes from one backend definition; the frontend holds no column list of
  its own.
- AC4. A photo and a drawing load for an anonymous customer (no login) and the payload carries no
  storage key or bucket path.
- AC5. At 375px no column is dropped; the table scrolls inside its own gutter, not the page.
