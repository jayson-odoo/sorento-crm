# TAG-UNION browser pass (cloud sandbox, agent-browser 0.27.0, 8 Nov)

Stack: backend uvicorn + `next dev` on the sandbox's bootstrapped DB (no prod data), superadmin login.
Seeded: tags "TU Sorento" (companies Sorento, AI replies off) and "TU Mocha" (companies ZZT Mocha, AI replies on), one contact.

1. PUT the contact's tags = both (the route the tag picker calls): DB holds both companies, AI replies on (union, live).
2. Sorento removed from the contact's companies by hand. Contact page, Tags section: "Companies / Own change ZZT Mocha / Tags say Sorento, ZZT Mocha" (`tags-own-change.png`, 1280 wide).
3. "Apply tag settings" (name kept): preview "1 will change, Companies + Sorento"; applied; DB holds both companies again; section reads "Everything matches its tags / No own changes." (`tags-375.png`, 375 wide, no clipping).
4. Contact Tags list (reached through the menu search): column header "Own changes", 0 for both tags.

Deviation: the sandbox's contact list rows did not open the contact page on click, so step 2 opened `/user-management/contacts/<id>` by URL; the Contact Tags page was reached by the menu search.
