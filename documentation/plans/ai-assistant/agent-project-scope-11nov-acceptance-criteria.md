# UAC: AI agent project tools scoped to what the asker can see (AGENT-PROJECT-SCOPE)

- AC-1 A user limited in projects (holds `projects.projects.view_own`, not `projects.projects.view`) who asks the AI panel how many projects there are, to list them, or who owns them, gets only the projects the Projects list shows them.
- AC-2 The same user asking about a project they cannot open in the app gets "not found", never its facts.
- AC-3 An admin (or a holder of `projects.projects.view`) gets the same answers as before.
- AC-4 Removing the filter turns a test red.
- AC-5 "My projects" (any phrasing naming the asker) is answered by filtering on the asker's own user id, with no resolve round: the agent may send `owner_user_ids: "me"`; a name or an id the turn never showed is still refused.
- AC-6 An answer about zero rows ("you own no projects", "0 found") after a read that matched nothing is not flagged, and a repair never writes a placeholder into a sentence: the sentence is left out and the reply says a figure was left out.
- AC-7 "Who owns them" gives each owner's count exactly as the Projects list holds it, from every matching project (not the rows that fit the result), and a wrong count written beside an owner's name is caught even when that number appears elsewhere in the result.
