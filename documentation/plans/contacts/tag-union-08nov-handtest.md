# Hand test - TAG-UNION (contact tags add up)

## URL
crew test copy

## Setup
1. Superadmin login. The test copy's backend has run `alembic upgrade head` (adds `respond_contacts.tag_settings_snapshot`).
2. Two companies exist (Sorento and Mocha). Pick one test contact with no tags, called "Test contact" below.
3. Contact tags screen: create tag "TU Sorento" with Access settings Companies = Sorento, and AI replies Off.
4. Create tag "TU Mocha" with Companies = Mocha, and AI replies On.

## Steps
1. Open Test contact, Tags: add "TU Sorento", save.
2. Look at the contact's Companies.
3. Add "TU Mocha" as well, save.
4. Look at Companies and the AI replies switch.
5. Remove "TU Mocha", save.
6. Look at Companies and AI replies.
7. Add Mocha to Companies by hand on the contact, save.
8. Remove "TU Sorento" from the contact, save.
9. Look at Companies.
10. Add "TU Sorento" back. On the Contact tags screen, switch "TU Sorento" to inactive.
11. Look at the contact's Companies.
12. Switch "TU Sorento" active again; on the contact, remove Sorento from Companies by hand, save; open Tags and press "Apply tag settings", confirm.
13. Log in as a user with contacts edit but not superadmin; try to add "TU Sorento" to another contact.

## Expected
1. Step 2: Companies = Sorento.
2. Step 4: Companies = Sorento and Mocha (before this change: none). AI replies = On.
3. Step 6: Companies = Sorento; AI replies = Off (what TU Sorento says).
4. Step 9: Companies = Mocha (the hand-added company stays; Sorento went with its tag).
5. Step 11: Companies = Mocha only (an inactive tag counts for nothing).
6. Step 12: after switching TU Sorento on, Companies = Sorento and Mocha. After the hand removal the Tags section lists Companies as an "Own change" (Companies = Mocha). After Apply, Companies = Sorento and Mocha and the section reads "Everything matches its tags".
7. Step 13: refused with "You may not add or remove a tag that sets Companies."; the contact keeps its tags.
