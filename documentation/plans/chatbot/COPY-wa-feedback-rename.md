# WA-COMPLAINT-INTAKE round 15: "idea" becomes "feedback" in the filing flow

Owner, 14 Nov ~23:20: "we need to generalize this to a better name instead of just idea otherwise it sounds really
like idea". Crew picked the words: EN "feedback", MS "maklum balas", ZH "反馈". The type stays shown:
EN "Problem report" / "Feature request", MS "Laporan masalah" / "Permintaan ciri", ZH "问题报告" / "功能需求".
Owner example: "Your feedback has been logged: Problem report - <title>".

In scope: every text a WhatsApp or CRM chat user reads in the filing flow. Out of scope (stay): internal names
(ideation module, tables, tool names such as `crm_idea_create`, registry key names), the CRM Ideas board's own page
name and screens, console trace labels, admin policy rows, record action buttons, the shared service numbering.

## How it ships

The copy lives in the prompt registry (`chatbot_reply_ideation_capture_*`, `.ms`, `.zh`), and `seed_prompt_registry`
is insert-only, so a seeded install keeps the stored text whatever the code says. A migration publishes each new
text as the next version and moves that key's `production` label ONLY where production still equals the stock text
it replaces (strip-normalised), the same way as `alembic/versions/idea_capture_fields_0001.py`. A text the owner
edited is left alone with a warning. A re-run is a no-op. Downgrade moves nothing back (the old versions stay in the
history and the owner can move the label on the Prompts page).

## The record number

Today the number shows as the shared service sends it ("IDEA-0184"). This round routes every place a user reads it
through ONE display function (`submission_types.display_number`), which returns it unchanged until crew answers the
crew-ask on how to show it. The copy carries it on its own line, "Number: {{idea_number}}".

## Reply copy (registry keys `chatbot_reply_ideation_capture_<name>`)

| name | EN | MS | ZH |
|---|---|---|---|
| no_access | You need a CRM login with access to send feedback here. Please ask your Sorento contact for one. | Anda perlukan log masuk CRM dengan akses untuk menghantar maklum balas di sini. Sila minta daripada orang perhubungan Sorento anda. | 您需要拥有相应权限的 CRM 登录账号，才能在这里提交反馈。请向您的 Sorento 联系人申请。 |
| unconfigured | Feedback isn't set up here yet, so I couldn't log that. Please try again later or reach out to the team. | Maklum balas belum disediakan di sini, jadi saya tidak dapat merekodkannya. Sila cuba lagi nanti atau hubungi pasukan kami. | 这里还没有开通反馈功能，所以我无法记录。请稍后再试，或联系我们的团队。 |
| ask_idea | Sure, what would you like changed? Tell me in one message. | Boleh! Apa yang anda mahu ubah? Beritahu saya dalam satu mesej. | 好的！您希望改进什么？请用一条消息告诉我。 |
| give_up | I still couldn't tell what you'd like changed. When you're ready, send it in one message. | Saya masih tidak pasti apa yang anda mahu ubah. Bila anda sudah bersedia, hantarkannya dalam satu mesej. | 我还是没能看出您想改进什么。准备好后，请用一条消息发送给我。 |
| similar_offered | You already sent feedback like this: | Anda sudah menghantar maklum balas yang serupa: | 您已经提交过类似的反馈： |
| similar_offered_reply | Reply a number to edit that one, or NEW to log this as new feedback. | Balas dengan nombor untuk mengedit yang itu, atau NEW untuk merekod ini sebagai maklum balas baharu. | 回复编号即可编辑该反馈，或回复 NEW 记录为新反馈。 |
| similar_offered_see_all | See all your feedback: {{link}} | Lihat semua maklum balas anda: {{link}} | 查看您的全部反馈：{{link}} |
| similar_picked | unchanged (no product word) | unchanged | unchanged |
| similar_picked_no_link | Open {{idea_number}} in the CRM to add this. | Buka {{idea_number}} di CRM untuk menambah ini. | 请在 CRM 中打开 {{idea_number}} 补充这些内容。 |
| complete | Your feedback has been logged: Feature request - {{title}}<br>Number: {{idea_number}}<br>Open it to add what I didn't catch:<br>{{missing}}<br>{{link}} | Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}<br>Nombor: {{idea_number}}<br>Buka untuk menambah apa yang saya tidak tangkap:<br>{{missing}}<br>{{link}} | 您的反馈已记录：功能需求 - {{title}}<br>编号：{{idea_number}}<br>打开它补充我没有记录到的内容：<br>{{missing}}<br>{{link}} |
| complete_no_link | Your feedback has been logged: Feature request - {{title}}<br>Number: {{idea_number}} | Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}<br>Nombor: {{idea_number}} | 您的反馈已记录：功能需求 - {{title}}<br>编号：{{idea_number}} |
| complete_issue | Your feedback has been logged: Problem report - {{title}}<br>Number: {{idea_number}} | Maklum balas anda telah direkodkan: Laporan masalah - {{title}}<br>Nombor: {{idea_number}} | 您的反馈已记录：问题报告 - {{title}}<br>编号：{{idea_number}} |
| type_refused | I couldn't file this: feedback of this type can't be taken yet. | Saya tidak dapat menghantar ini: maklum balas jenis ini belum boleh diterima. | 我无法提交这个：暂时不接受此类型的反馈。 |
| error | Sorry, I couldn't save that feedback just now. Please try again in a moment. | Maaf, saya tidak dapat menyimpan maklum balas itu sekarang. Sila cuba lagi sebentar nanti. | 抱歉，我暂时无法保存这条反馈，请稍后再试。 |
| config_error | Feedback isn't set up correctly here, so I couldn't save that. Please let your Sorento contact know. | Maklum balas tidak disediakan dengan betul di sini, jadi saya tidak dapat menyimpannya. Sila maklumkan kepada wakil Sorento anda. | 此处的反馈设置不正确，所以我无法保存。请告知您的 Sorento 联系人。 |

`<br>` above is a newline in the copy. `give_up_issue` (round 14) uses the same words (feedback, never idea).

## Code-built and agent text (EN, as today)

- `agent/writes.py` note put in the reply by code: "Feedback {number}: {link}." / "The feedback: {link}." and the test
  tail "This is test feedback, so it is not on the board."
- `agent/writes.py` proposal summary (the card and the step chip): `Log feedback (Problem report) "<title>": ...` /
  `Log feedback (Feature request) "<title>": ...`; the similar tail "Similar feedback of yours: ...".
- `agent/writes.py` messages the model reads and repeats (`IDEA_NOT_CREATED`, `IDEA_OWN_ONLY`,
  `IDEA_ALREADY_CAPTURED`, `IDEA_REFUSED`, `IDEA_TYPE_REFUSED` and the inline ones): "idea" becomes "feedback"
  ("the Ideas workspace" becomes "the feedback service").
- `agent/writes.py` tool descriptions (model-facing): the user-facing noun is feedback; one sentence tells the model to
  call it feedback when talking to the user and to name the type (Problem report / Feature request), never "idea".
- `agent/tools.py` labels: "record feedback: a wish or feature request, or a problem with the CRM system or the
  assistant", "change your feedback", "your feedback".
- `agent/loop.py` confirm note: "The feedback's number and link are added to your reply automatically. Do not write
  them."
- `chatbot/lanes/ideate.py` `PANEL_IDEAS_REPLY`: "Thanks! You can log and track feedback on the Ideas board - open it
  here: /ideas" (the board keeps its page name).
- `ideation_turn_service` reminder: 'Your feedback "{title}" is still open. Reply to finish it, or say cancel.'
- `ideation_status_update_service` session text: "Update on your feedback {number}: it is now {status}." An approved
  WhatsApp template keeps its approved text (Meta approval); reported, not changed.
- `submission_types` labels: "Problem report" / "Feature request" (the `issue` key keeps its value). The CRM Ideas
  board's Type column follows the label; its user guide is updated in the same PR.
- `lanes/canned.py` access denied for the ideation agent names "feedback", not "ideation".
