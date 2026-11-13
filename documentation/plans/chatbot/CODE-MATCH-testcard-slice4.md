# CHATBOT-CODE-MATCH slice 4: 10:00 test card (Chatbot Console, dry run, no WhatsApp send)

PR #2370, slice 4: a size is read ONLY from a product's stored size (the size key Settings > Spec Registry gives its
category) or from a number in the typed code that equals such a stored value. No default size, ever. Applies when the
message names ONE product code; several codes plus a size behave as today. Use a water closet family in the test copy
where one member stores a trap length and another does not (the review's example: SRTWC8152-SH-UF and its sized
siblings).

| # | Contact | Type | Before (main) | After (this slice) |
| --- | --- | --- | --- | --- |
| 1 | dealer | `SRTWC8152-SH-UF-250 x 1` | "Couldn't find" or a list of codes with no sizes | "Couldn't find SRTWC8152-SH-UF-250. Did you mean:" each close code on its own line with its stored size ("Trap outlet length: 300 mm") or "not recorded"; nothing answered as 250 |
| 2 | staff | `8152-300-SH stock` | `Couldn't find: "8152-300-SH"` | `Did you mean` SRTWC8152-SH-300 with its stored 300 mm (offered, not answered) |
| 3 | dealer | `SRTWC8152-SH-UF 400mm` (a size no member stores) | "None with size 400 mm." then the stock of SRTWC8152-SH-UF | "Couldn't find SRTWC8152-SH-UF with size 400 mm. Did you mean:" with the family's stored sizes; nothing answered |
| 4 | staff | `srtwc8152 sh uf 400mm` (spaced) | same as 3, answered | same as 3 in the staff wording |
| 5 | dealer | `<another code> x 2, SRTWC8152-SH-UF 300mm` | both codes handled as today | unchanged: both handled exactly as today |

Data list (no data edit): `sorento_crm_backend/scripts/chatbot_products_without_size.sql` lists active products in
categories with a size key and no stored size (the review counted 419 of 979 water closets); crew runs it on the dev copy.
