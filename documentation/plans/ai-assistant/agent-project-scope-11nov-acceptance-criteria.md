# UAC: AI agent project tools scoped to what the asker can see (AGENT-PROJECT-SCOPE)

- AC-1 A user limited in projects (holds `projects.projects.view_own`, not `projects.projects.view`) who asks the AI panel how many projects there are, to list them, or who owns them, gets only the projects the Projects list shows them.
- AC-2 The same user asking about a project they cannot open in the app gets "not found", never its facts.
- AC-3 An admin (or a holder of `projects.projects.view`) gets the same answers as before.
- AC-4 Removing the filter turns a test red.
