## URL
crew test copy

## Setup
- Dev DB has the two columns from the `crew-migration:` comment (`projects.projects.name`, `projects.leads.name`).
- Sign in as a sales manager (projects edit + manage + registrations approve).
- AI extract needs the dev AI provider key (as for the existing AI extract button).

## Steps
1. From `/`, click Project sales in the sidebar, then Projects.
2. Click "Register a project".
3. Look at page 1.
4. Paste into Project title: CADANGAN MEMBINA 54 UNIT RUMAH TERES DUA TINGKAT DI ATAS LOT 161268, 161269 & 161270, JALAN PERMATANG BADAK PERDANA, MUKIM KUALA KUANTAN, DAERAH KUANTAN, PAHANG DARUL MAKMUR.
5. Click AI extract, then AI Extract in the dialog, wait for the review.
6. Click "Confirm and prefill".
7. Pick any developer, click Check, then Next.
8. Look at the first field of "Who and what" on page 2.
9. Replace the name with: Permatang Badak Perdana Plot 1
10. Pick a lead source, click Register project.
11. On the new project's page, look at the header and at the "The development" card.
12. Go back to Projects, type "Permatang Badak" in the search box.
13. Open the project, gear, Edit project; clear Project name; Save.
14. Look at the project header.
15. Edit again; type a name of 81 characters into Project name.
16. Project sales, Leads, New lead: fill the title, Project name "Taman Contoh Lead", a customer; save; open the lead.
17. Qualify the lead into a project.
18. Dealer portal: open a Project registration form as a portal contact.

## Expected
1. Page 1 shows only Project title, AI extract, Developer and the Check result. No Project name field.
2. The AI review lists a "Project name" row with a short name (e.g. "54 Teres 2 Tingkat, Permatang Badak Perdana"), no lot numbers.
3. Page 2 "Who and what" opens with Project name filled with that proposal, counter "n / 80", then Project type.
4. The project header shows "Permatang Badak Perdana Plot 1", not the long title.
5. "The development" starts with Project title showing the full CADANGAN text (3 lines, eye icon for the rest), then Developer.
6. The Projects list finds the project; its Project column shows "Permatang Badak Perdana Plot 1"; hovering shows the full title.
7. After clearing the name, the header shows the title clamped to 2 lines (as before this lane).
8. The name input stops at 80 characters.
9. The lead page header shows "Taman Contoh Lead" and a Title fact with the lead's title.
10. The qualified project's header shows "Taman Contoh Lead".
11. The portal registration form shows "Project name" right after "Project title"; its AI extract fills it.
