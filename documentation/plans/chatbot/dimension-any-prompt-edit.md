# DIMENSION-ANY: optional parser prompt edit (lookup-lists versions)

Status: proposal for crew. Load it as a lane dev version on top of the live parser text (v188 = prod v69) and
run the Gemini eval A/B against the same text without it. The lane's code works without it: the Spec lookup list
now offers `Size 150mm, any dimension (size: 150)` first for a length, and the parser takes spec_key/spec_value
from the bracket of the line it picks. This edit only says, in the prompt, which line to pick when.

The prod text is not in this public repo, so the edit is anchored on the sentence the CHAT-SLIM-INDEX lookup edits
wrote into it (`app/services/chatbot_lookup_edits.py`, "spec_key source"):

```diff
-the key in the "(key: value)" bracket of a Spec candidates line of the user message, or null
+the key in the "(key: value)" bracket of a Spec candidates line of the user message, or null. A measurement the message gives with no dimension named ("150mm", "15 cm", "10 inch") is the "(size: N)" line; a dimension's own line ("Length 150mm (dim_length: 150)") only when the message names that dimension, in any language
```

If the anchor is not found exactly once in the version crew uses, apply nothing and tell the lane.
