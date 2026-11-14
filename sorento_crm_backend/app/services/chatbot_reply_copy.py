"""The WhatsApp bot's canned sentences, verbatim from `escalate-catalog.js` (AC-302).

**Why this file sits OUTSIDE `app/services/chatbot/`.** `ai_prompt_registry` is a core
service and core must never import the chatbot package (AC-002, the import-boundary
test). The registry needs these strings as its fallback bodies, so they live here, next
to `chatbot_parser_prompt.py`, which exists for exactly the same reason. The package's
own `copy.py` imports them back the other way, which the boundary allows.

Journey B is what this is for: the owner opens Settings > AI Prompts, edits the
not-supported reply, publishes, and the next WhatsApp turn uses it. The strings below
are what ships and what a DB-unreachable turn falls back to - D8, parity before
improvement, so they are character-for-character today's `switch`.

**The escalate prefix is a contract, not a wording choice.** `output_exchange`'s
`offeredEscalation` matches `/would you like me to escalate/i` against the bot's OWN
persisted reply, which is how an accepted offer is recognised next turn. Reword the
prefix and ladder rank 2 dies silently on every accepted offer. R3's `pending` marker is
the structural replacement, and it is written from S2 - but the regex reader stays until
S8, so the prefix stays byte-stable until then.
"""
from __future__ import annotations

# `case 'demand_qty'`
CHATBOT_REPLY_DEMAND_QTY = "Please specify your demand quantity"

# `case 'not_supported'`. The DOMAIN LIST becomes
# `system_settings.chatbot_unsupported_domains` at S3 (AC-304); the SENTENCE is here.
CHATBOT_REPLY_NOT_SUPPORTED = (
    "Sorry, we don't support direct goods receive & SPO at the moment. You may ask "
    "about incoming stock for a specific product or container"
)

# `case 'clarify_menu'`. `{{user_goal}}` is n8n's `${qf.user_goal}` - the parser's own
# phrase for what the customer is trying to do.
CHATBOT_REPLY_CLARIFY_MENU = (
    "I see you're {{user_goal}}, Let me understand more.\n\n"
    "Are you asking about any of these?\n\n"
    "- Product (List Price, Dimension)\n"
    "- Photos, Technical Specs, Cert\n"
    "- Promotion\n"
    "- Forms\n"
    "- Stock\n"
    "- Delivery order\n"
    "- Incoming\n"
    "- Catalogue, Warranty\n\n"
    "I can help with the topics listed above."
)

# `case 'escalate_offer'`, both halves. TWO KEYS, not one with a blank: the no-team form
# is a DIFFERENT sentence ("this to our team"), and substituting an empty `{{team}}`
# would send "escalate to  team?" to a customer.
CHATBOT_REPLY_ESCALATE_OFFER = (
    "I am sorry the provided answer does not meet your requirements. Would you like me "
    "to escalate to {{team}} team?"
)
CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM = (
    "I am sorry the provided answer does not meet your requirements. Would you like me "
    "to escalate this to our team?"
)

# `case 'out_of_scope'` - a note for the human who picks the thread up, never sent to the
# customer (`includeResponse = false`). Its `{{team}}` is the RAW slug: the JS
# interpolates `qf.routing.suggested_team` directly here while the escalate-offer arm
# runs it through `_prettyTeam`, and this text is internal.
CHATBOT_REPLY_OUT_OF_SCOPE = (
    "Informed the user that request is out of scope and will proceed to escalate to "
    "the {{team}} team"
)
CHATBOT_REPLY_OUT_OF_SCOPE_NO_TEAM = (
    "Informed the user that request is out of scope and will proceed to escalate to "
    "the appropriate team"
)

# `case 'escalation_declined'` - FIXED canned reply, no LLM shaping.
CHATBOT_REPLY_ESCALATION_DECLINED = "Escalation declined."

# R22(a) (owner round 9, 13 Sep 2026): the customer said no to an OFFER the bot made -
# the outstanding detail list, or the scope question. One short line and nothing else:
# the first cut answered it with `clarify_menu` ("I see you're trying to decline, Let me
# understand more. Are you asking about any of these? ...") and that is the wrong tone
# for "no" - it re-opens a conversation the customer just closed. `escalation_declined`
# above is the nearest thing that existed and it names an escalation nobody asked for,
# so this is its sibling for every other offer. Editable by the owner like every key in
# this table: the wording is a row in the prompt registry, not a string in a deploy.
CHATBOT_REPLY_OFFER_DECLINED = "Okay, noted."

# What the customer reads when a turn could not be finished - byte-identical to what the
# spine sends today when `sub-query-reformulator` fails (`sub-error-logger`).
#
# **It lives here, not in the package, because the ENDPOINT sends it.** The head returns
# it as an action on a failed parse and the tail's route returns it when the tail raises,
# so a copy inside `app/services/chatbot/` would have to be re-exported and the package's
# "one public entry point" rule (D3, `test_import_boundary.py`) would have to be widened
# for a string. NOT a registry key: an owner editing it in Settings could leave a failed
# turn with no words at all, and this is the one sentence that must always exist.
CHATBOT_TURN_ERROR_REPLY = (
    "Sorry, I ran into a problem understanding that. Please try again in a moment."
)

# CHATBOT-FAIL-TRIAGE (owner rule, 30 Oct 2026): the bot never replies the generic apology
# above or `llm_call.RATE_LIMITED_REPLY`. Each failure says what actually went wrong. All are
# whole sentences with MS / ZH entries in `chatbot/label_catalog.py`, which prints them in the
# contact's language at the final reply pass. The real reason stays in `chatbot.turns.error`.
CHATBOT_REPLY_AI_DID_NOT_ANSWER = (
    "I could not read your message just now because our AI service did not answer. Please send it again."
)
CHATBOT_REPLY_TURN_FAILED = (
    "I hit an error while answering this and could not finish it. Please send it again."
)
CHATBOT_REPLY_PREVIOUS_STILL_RUNNING = (
    "I was still answering your previous message, so I could not take this one. Please send it again."
)
CHATBOT_REPLY_ESCALATION_FAILED = "I could not pass this to the {team} team just now. Please contact them directly."
# Review round 2 S1: the same failure when there is no reachable topic-map team to name.
CHATBOT_REPLY_ESCALATION_FAILED_NO_TEAM = "I could not pass this to our team just now. Please contact us directly."
CHATBOT_REPLY_NONE_FOUND = "No current {label} found for {subject}."
CHATBOT_REPLY_ASK_SUBJECT = "Which customer or salesperson should I check the {label} for?"
CHATBOT_REPLY_ASK_PRODUCT = "Which product do you want the {label} for? Send me the code."
CHATBOT_REPLY_REPORT_NOT_PERMITTED = "That report is not available on your account."

# `sorento-sub-respond-sendmsg-respond5`'s `message` expression - the ENTIRE reply on the
# access-denied lane, which never reaches `compile-current-state` at all. `{{team}}` is
# the parser's `suggested_agent`, em-dash folded to a hyphen by the caller (the fold is
# n8n's own, on the agent name, not on this sentence).
CHATBOT_REPLY_ACCESS_DENIED = "Sorry, you are not allowed to access {{team}}"

# `offer-hold-reply.js`'s closing clause. The LEAD ("Both *A* and *B* teams are listed")
# is a function of how many companies the pool holds, so it is composed in
# `lanes/canned.offer_hold_clarify_text` rather than templated - a count is not a
# substitution. What IS editable is this clause, and it carries the leading separator so
# an owner can reword the whole tail of the sentence in one place.
CHATBOT_REPLY_OFFER_HOLD = (
    " - reply a number, a name, or the company ({{companies}}) and I'll assign automatically."
)
# The same clause for a pool that carries NO company names. A DIFFERENT sentence, not this
# one with a blank in it: the parser's company-pick arm refuses every pick against an
# empty pool, so inviting a reply that cannot resolve would be worse than not offering it.
CHATBOT_REPLY_OFFER_HOLD_NO_COMPANIES = (
    " - reply a number or a name and I'll assign automatically."
)


# --------------------------------------------------------------------------- #
# S4 graceful fallback (PLAN-chatbot-memory-26sep.md section 7.2, AC-MEM089). NEW
# templates only: every string above stays byte-identical. A reply is
# `ack + memory_line + offer`; the ack is the clarifier's, these are the other two
# halves plus the canned ack the guard falls back to. Each has an English base key
# and `.ms` / `.zh` variants, picked by the contact's saved language, else the
# clarifier's, else English (`chatbot/copy.py::CannedCopy.render_in`). The
# escalation offer wording is NOT among them: the accepted-offer regex still reads
# it (module docstring).
# --------------------------------------------------------------------------- #

#: What replaces an ack the guard refused (it named a figure, code, price or date
#: its own input never had), and what a history reply opens with when the
#: clarifier could not be reached.
CHATBOT_REPLY_FALLBACK_ACK = {"en": "Noted.", "ms": "Baik.", "zh": "好的。"}
#: The offer when memory holds nothing to build on (Off, or a first-time contact):
#: a concrete next step, the domain menu in one line (AC-MEM091).
CHATBOT_REPLY_FALLBACK_OFFER = {
    "en": "What can I check for you? Stock, incoming, delivery orders, promotions or product details.",
    "ms": "Apa yang saya boleh semak untuk anda? Stok, barang masuk, pesanan penghantaran, promosi atau butiran produk.",
    "zh": "需要我帮您查什么？库存、到货、送货单、促销或产品资料。",
}
#: The memory line naming the newest conversation, then the re-run offer.
CHATBOT_REPLY_FALLBACK_LAST_TIME = {
    "en": "Last time: {{summary}}.",
    "ms": "Kali terakhir: {{summary}}.",
    "zh": "上次：{{summary}}。",
}
CHATBOT_REPLY_FALLBACK_OFFER_RERUN = {
    "en": "Want me to check any of that again, or something new?",
    "ms": "Mahu saya semak semula, atau perkara lain?",
    "zh": "要我再查一次，还是查别的？",
}
#: The offer from the contact's usual products (and usual site), Full memory only.
CHATBOT_REPLY_FALLBACK_OFFER_USUAL = {
    "en": "Want me to check stock for {{products}}, or something new?",
    "ms": "Mahu saya semak stok {{products}}, atau perkara lain?",
    "zh": "要我查一下{{products}}的库存，还是查别的？",
}
CHATBOT_REPLY_FALLBACK_OFFER_USUAL_SITE = {
    "en": "Want me to check {{site}} stock for {{products}}, or something new?",
    "ms": "Mahu saya semak stok {{site}} untuk {{products}}, atau perkara lain?",
    "zh": "要我查一下{{site}}的{{products}}库存，还是查别的？",
}
#: A message the bot cannot place (`unknown`) from a contact linked to a customer:
#: the live CRM link names the customer, two numbered options (plan 7.3 example 6).
CHATBOT_REPLY_FALLBACK_OFFER_CUSTOMER = {
    "en": (
        "Want me to check the outstanding DOs for {{customer}} now, or pass this to the "
        "{{team}} team?\n1. Check outstanding DOs\n2. {{team}} team"
    ),
    "ms": (
        "Mahu saya semak DO tertunggak untuk {{customer}} sekarang, atau serahkan kepada "
        "pasukan {{team}}?\n1. Semak DO tertunggak\n2. Pasukan {{team}}"
    ),
    "zh": "要我现在查{{customer}}未完成的送货单，还是转给{{team}}团队？\n1. 查未完成的送货单\n2. {{team}}团队",
}
#: A fact the dealer just stated, confirmed back (plan 7.3 examples 7 and 9).
CHATBOT_REPLY_FALLBACK_NOTED_ROLE = {
    "en": "I've noted you're the {{role}} at {{customer}}.",
    "ms": "Saya sudah catat anda {{role}} di {{customer}}.",
    "zh": "已记下您是{{customer}}的{{role}}。",
}
CHATBOT_REPLY_FALLBACK_NOTED_ROLE_NO_CUSTOMER = {
    "en": "I've noted you're the {{role}}.",
    "ms": "Saya sudah catat anda {{role}}.",
    "zh": "已记下您是{{role}}。",
}
CHATBOT_REPLY_FALLBACK_NOTED_LANGUAGE = {
    "en": "From now on I'll reply in English.",
    "ms": "Lepas ni saya balas dalam Bahasa Melayu.",
    "zh": "以后我会用中文回复。",
}
CHATBOT_REPLY_FALLBACK_NOTED = {
    "en": "I've noted that.",
    "ms": "Saya sudah catat.",
    "zh": "已记下。",
}
#: The history reply (AC-MEM082): the lead, the numbered list (built in code), the
#: re-run offer; or the one line saying memory holds nothing yet.
CHATBOT_REPLY_HISTORY_LEAD = {
    "en": "Here's what you checked with me recently:",
    "ms": "Ini yang anda semak dengan saya baru-baru ini:",
    "zh": "这是您最近向我查询的内容：",
}
CHATBOT_REPLY_HISTORY_OFFER = {
    "en": "Reply with a number and I'll run it again with today's figures.",
    "ms": "Balas dengan nombor dan saya akan semak semula dengan angka hari ini.",
    "zh": "回复编号，我会用今天的数据重新查询。",
}
CHATBOT_REPLY_HISTORY_NOTHING = {
    "en": "I don't have an earlier conversation with you on record yet.",
    "ms": "Saya belum ada rekod perbualan kita sebelum ini.",
    "zh": "我这里还没有我们之前的对话记录。",
}
#: A follow-up the parser resolved from memory opens its answer with what it
#: carried (AC-MEM083): from a closed conversation, or from the usual products.
CHATBOT_REPLY_CARRIED_EPISODE = {
    "en": "Carrying on from {{day}}: {{subject}}.",
    "ms": "Sambungan dari {{day}}: {{subject}}.",
    "zh": "接着{{day}}的：{{subject}}。",
}
CHATBOT_REPLY_CARRIED_USUAL = {
    "en": "Your usual: {{products}}.",
    "ms": "Biasa anda: {{products}}.",
    "zh": "您常查的：{{products}}。",
}
#: A commercial ask handed over with the linked salesperson named (AC-MEM087).
#: Sent in place of the lane's "routed to the respective person-in-charge" line;
#: routing, assignment, the comment and the SLA row are the lane's, unchanged.
CHATBOT_REPLY_HANDOVER_SALESPERSON = {
    "en": (
        "{{salesperson}} looks after your account. I've passed your request to the "
        "{{team}} team for {{salesperson}}. We will get back to you soon."
    ),
    "ms": (
        "{{salesperson}} menguruskan akaun anda. Saya sudah serahkan permintaan anda kepada "
        "pasukan {{team}} untuk {{salesperson}}. Kami akan hubungi anda nanti."
    ),
    "zh": "{{salesperson}}负责您的账户。我已把您的请求转给{{team}}团队交给{{salesperson}}，我们会尽快回复您。",
}

# --------------------------------------------------------------------------- #
# IDEATION-CAPTURE (PLAN-ideation-capture-02oct.md section 4a): the replies of the
# one-message ideation turn. Rendered by `ideation_capture_replies.render_reply`.
# The idea number, title, links and the missing-field names (English in every
# language, owner: "exact") are tokens filled by code; the numbered similar-idea
# lines are built in code between the lead and the reply line.
# --------------------------------------------------------------------------- #
IDEATION_CAPTURE_NO_ACCESS = {
    "en": "You need a CRM login with access to send feedback here. Please ask your Sorento contact for one.",
    "ms": (
        "Anda perlukan log masuk CRM dengan akses untuk menghantar maklum balas di sini. "
        "Sila minta daripada orang perhubungan Sorento anda."
    ),
    "zh": "您需要拥有相应权限的 CRM 登录账号，才能在这里提交反馈。请向您的 Sorento 联系人申请。",
}
IDEATION_CAPTURE_UNCONFIGURED = {
    "en": (
        "Feedback isn't set up here yet, so I couldn't log that. Please try again later or reach out "
        "to the team."
    ),
    "ms": (
        "Maklum balas belum disediakan di sini, jadi saya tidak dapat merekodkannya. "
        "Sila cuba lagi nanti atau hubungi pasukan kami."
    ),
    "zh": "这里还没有开通反馈功能，所以我无法记录。请稍后再试，或联系我们的团队。",
}
IDEATION_CAPTURE_ASK_IDEA = {
    "en": "Sure, what would you like changed? Tell me in one message.",
    "ms": "Boleh! Apa yang anda mahu ubah? Beritahu saya dalam satu mesej.",
    "zh": "好的！您希望改进什么？请用一条消息告诉我。",
}
#: The ask-back was answered twice with nothing to file in it: a statement, not another question.
IDEATION_CAPTURE_GIVE_UP = {
    "en": "I still couldn't tell what you'd like changed. When you're ready, send it in one message.",
    "ms": (
        "Saya masih tidak pasti apa yang anda mahu ubah. Bila anda sudah bersedia, hantarkannya "
        "dalam satu mesej."
    ),
    "zh": "我还是没能看出您想改进什么。准备好后，请用一条消息发送给我。",
}
#: WA-COMPLAINT-INTAKE round 14: an issue flow's answer held no words to file. The general word
#: (owner 14 Nov 23:20): feedback / maklum balas / 反馈, never idea.
IDEATION_CAPTURE_GIVE_UP_ISSUE = {
    "en": (
        "I still could not tell what went wrong. When you are ready, send what you saw and where, "
        "in one message, and I will log it as feedback."
    ),
    "ms": (
        "Saya masih tidak dapat tahu apa yang tidak kena. Bila anda sudah bersedia, hantar apa yang "
        "anda nampak dan di mana dalam satu mesej, dan saya akan merekodkannya sebagai maklum balas."
    ),
    "zh": "我还是没能弄清楚出了什么问题。准备好后，请在一条消息里告诉我您看到了什么、在哪里看到的，我会把它记录为反馈。",
}
#: Rounds 14-15 review B1: the answer to the issue ask was a cancel. Nothing was filed.
IDEATION_CAPTURE_CANCELLED = {
    "en": "Okay, I've dropped that. Nothing was logged.",
    "ms": "Baik, saya batalkan. Tiada apa-apa direkodkan.",
    "zh": "好的，已取消，没有记录任何内容。",
}
#: AI-KEY-PER-PROVIDER: the message could not be read at all (provider or key error, timeout).
#: Not "no idea": a plain statement of what happened, no apology, no question.
IDEATION_CAPTURE_READ_FAILED = {
    "en": "I couldn't read that just now. Please send it again.",
    "ms": "Saya tidak dapat membaca mesej itu sekarang. Sila hantar sekali lagi.",
    "zh": "我刚才无法读取这条消息，请再发送一次。",
}
IDEATION_CAPTURE_SIMILAR_OFFERED = {
    "en": "You already sent feedback like this:",
    "ms": "Anda sudah menghantar maklum balas yang serupa:",
    "zh": "您已经提交过类似的反馈：",
}
IDEATION_CAPTURE_SIMILAR_OFFERED_REPLY = {
    "en": "Reply a number to edit that one, or NEW to log this as new feedback.",
    "ms": (
        "Balas dengan nombor untuk mengedit yang itu, atau NEW untuk merekod ini sebagai "
        "maklum balas baharu."
    ),
    "zh": "回复编号即可编辑该反馈，或回复 NEW 记录为新反馈。",
}
IDEATION_CAPTURE_SIMILAR_OFFERED_SEE_ALL = {
    "en": "See all your feedback: {{link}}",
    "ms": "Lihat semua maklum balas anda: {{link}}",
    "zh": "查看您的全部反馈：{{link}}",
}
IDEATION_CAPTURE_SIMILAR_PICKED = {
    "en": "Open {{idea_number}} to add this: {{link}}",
    "ms": "Buka {{idea_number}} untuk menambah ini: {{link}}",
    "zh": "打开 {{idea_number}} 补充这些内容：{{link}}",
}
#: No CRM base URL to build a link from: point at the page instead of a blank link.
IDEATION_CAPTURE_SIMILAR_PICKED_NO_LINK = {
    "en": "Open {{idea_number}} in the CRM to add this.",
    "ms": "Buka {{idea_number}} di CRM untuk menambah ini.",
    "zh": "请在 CRM 中打开 {{idea_number}} 补充这些内容。",
}
IDEATION_CAPTURE_COMPLETE = {
    "en": (
        "Your feedback has been logged: Feature request - {{title}}\n"
        "Number: {{idea_number}}\n"
        "Open it to add what I didn't catch:\n"
        "{{missing}}\n"
        "{{link}}"
    ),
    "ms": (
        "Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}\n"
        "Nombor: {{idea_number}}\n"
        "Buka untuk menambah apa yang saya tidak tangkap:\n"
        "{{missing}}\n"
        "{{link}}"
    ),
    "zh": (
        "您的反馈已记录：功能需求 - {{title}}\n"
        "编号：{{idea_number}}\n"
        "打开它补充我没有记录到的内容：\n"
        "{{missing}}\n"
        "{{link}}"
    ),
}
#: Created, but no safe CRM link could be built: a DIFFERENT sentence, not the one
#: above with a blank link (the same two-key rule as `escalate_offer`).
IDEATION_CAPTURE_COMPLETE_NO_LINK = {
    "en": "Your feedback has been logged: Feature request - {{title}}\nNumber: {{idea_number}}",
    "ms": "Maklum balas anda telah direkodkan: Permintaan ciri - {{title}}\nNombor: {{idea_number}}",
    "zh": "您的反馈已记录：功能需求 - {{title}}\n编号：{{idea_number}}",
}
#: WA-COMPLAINT-INTAKE (UAC I-2, I-3): an issue (something wrong with the CRM or the assistant).
#: The filed reply is one fact per line (round 15: the head line names the type and the title, then the
#: number); the Photos line (only when photos landed) and the link line are added by code after these two.
IDEATION_CAPTURE_ASK_ISSUE = {
    "en": "What went wrong? Tell me what you saw and where.",
    "ms": "Apa yang tidak kena? Beritahu saya apa yang anda nampak dan di mana.",
    "zh": "出了什么问题？请告诉我您看到了什么，在哪里看到的。",
}
IDEATION_CAPTURE_COMPLETE_ISSUE = {
    "en": "Your feedback has been logged: Problem report - {{title}}\nNumber: {{idea_number}}",
    "ms": "Maklum balas anda telah direkodkan: Laporan masalah - {{title}}\nNombor: {{idea_number}}",
    "zh": "您的反馈已记录：问题报告 - {{title}}\n编号：{{idea_number}}",
}
IDEATION_CAPTURE_COMPLETE_ISSUE_PHOTOS = {
    "en": "Photos: {{count}}",
    "ms": "Gambar: {{count}}",
    "zh": "照片：{{count}}",
}
#: WA-COMPLAINT-INTAKE D-4: a console (test) turn of a dealer with no CRM user yet creates nothing.
IDEATION_CAPTURE_TEST_TURN = {
    "en": "Test turn: nothing was sent.",
    "ms": "Giliran ujian: tiada apa-apa dihantar.",
    "zh": "测试对话：没有发送任何内容。",
}
#: Round 6 (review 5): the dealer's own CRM user could not be set up (its phone already on another
#: user, the role missing). Said plainly; the cause is logged.
IDEATION_CAPTURE_ACCOUNT_FAILED = {
    "en": "I couldn't set up your account to file this. Please ask your salesperson.",
    "ms": "Saya tidak dapat menyediakan akaun anda untuk menghantar ini. Sila tanya jurujual anda.",
    "zh": "我无法为您设置账户来提交这个内容。请联系您的销售人员。",
}
#: SS #235: ss refused the item's type (a 422 `unknown_type` on create only). Plain words, no retry.
IDEATION_CAPTURE_TYPE_REFUSED = {
    "en": "I couldn't file this: feedback of this type can't be taken yet.",
    "ms": "Saya tidak dapat menghantar ini: maklum balas jenis ini belum boleh diterima.",
    "zh": "我无法提交这个：暂时不接受此类型的反馈。",
}
IDEATION_CAPTURE_ERROR = {
    "en": "Sorry, I couldn't save that feedback just now. Please try again in a moment.",
    "ms": "Maaf, saya tidak dapat menyimpan maklum balas itu sekarang. Sila cuba lagi sebentar nanti.",
    "zh": "抱歉，我暂时无法保存这条反馈，请稍后再试。",
}

IDEATION_CAPTURE_CONFIG_ERROR = {
    "en": "Feedback isn't set up correctly here, so I couldn't save that. Please let your Sorento contact know.",
    "ms": (
        "Maklum balas tidak disediakan dengan betul di sini, jadi saya tidak dapat menyimpannya. "
        "Sila maklumkan kepada wakil Sorento anda."
    ),
    "zh": "此处的反馈设置不正确，所以我无法保存。请告知您的 Sorento 联系人。",
}

# DEV-FAILURES RC-B (owner approved 12 Oct): a portal link reply names the form the link opens;
# the bare line is for a link that opens no particular form.
CHATBOT_REPLY_PORTAL_LINK = {
    "en": "Here is your portal link.",
    "ms": "Berikut pautan portal anda.",
    "zh": "这是您的门户链接。",
}
CHATBOT_REPLY_PORTAL_LINK_COMPLAINT = {
    "en": "Here is your portal link for a complaint.",
    "ms": "Berikut pautan portal anda untuk aduan.",
    "zh": "这是您提交投诉的门户链接。",
}
CHATBOT_REPLY_PORTAL_LINK_STOCK_INQUIRY = {
    "en": "Here is your portal link for a stock inquiry.",
    "ms": "Berikut pautan portal anda untuk pertanyaan stok.",
    "zh": "这是您提交库存查询的门户链接。",
}
CHATBOT_REPLY_PORTAL_LINK_PURCHASE_REQUEST = {
    "en": "Here is your portal link for a purchase request.",
    "ms": "Berikut pautan portal anda untuk permintaan pembelian.",
    "zh": "这是您提交采购申请的门户链接。",
}
CHATBOT_REPLY_PORTAL_LINK_SPONSORSHIP_FORM = {
    "en": "Here is your portal link for the sponsorship form.",
    "ms": "Berikut pautan portal anda untuk borang tajaan.",
    "zh": "这是您填写赞助表格的门户链接。",
}
# CHATBOT-FAIL-TRIAGE AC-3 / R1: the price tag request form is a portal link target
# (`portal_service.LINK_TYPES`), so its link names the form like the four above.
CHATBOT_REPLY_PORTAL_LINK_PRICE_TAG_REQUEST = {
    "en": "Here is your portal link for a price tag request.",
    "ms": "Berikut pautan portal anda untuk permintaan tanda harga.",
    "zh": "这是您申请价格标签的门户链接。",
}

# Release gate #1829, round 7 (crew ruling): the one acknowledgement of a reset turn ("clear
# all"). Nothing is looked up on that turn, so the sentence promises nothing.
CHATBOT_REPLY_RESET_ACK = {
    "en": "Okay, I've cleared that. What would you like to check?",
    "ms": "Baik, saya sudah kosongkan. Apa yang anda mahu semak?",
    "zh": "好的，已清除。您想查询什么？",
}

#: `short name -> (per-language text, declared {{tokens}})`, expanded below into one
#: registry key per language: `chatbot_reply_<name>` (English) and
#: `chatbot_reply_<name>.ms` / `.zh`.
FALLBACK_REPLY_COPY: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "portal_link": (CHATBOT_REPLY_PORTAL_LINK, ()),
    "portal_link_complaint": (CHATBOT_REPLY_PORTAL_LINK_COMPLAINT, ()),
    "portal_link_stock_inquiry": (CHATBOT_REPLY_PORTAL_LINK_STOCK_INQUIRY, ()),
    "portal_link_purchase_request": (CHATBOT_REPLY_PORTAL_LINK_PURCHASE_REQUEST, ()),
    "portal_link_sponsorship_form": (CHATBOT_REPLY_PORTAL_LINK_SPONSORSHIP_FORM, ()),
    "portal_link_price_tag_request": (CHATBOT_REPLY_PORTAL_LINK_PRICE_TAG_REQUEST, ()),
    "fallback_ack": (CHATBOT_REPLY_FALLBACK_ACK, ()),
    "reset_ack": (CHATBOT_REPLY_RESET_ACK, ()),
    "fallback_offer": (CHATBOT_REPLY_FALLBACK_OFFER, ()),
    "fallback_last_time": (CHATBOT_REPLY_FALLBACK_LAST_TIME, ("summary",)),
    "fallback_offer_rerun": (CHATBOT_REPLY_FALLBACK_OFFER_RERUN, ()),
    "fallback_offer_usual": (CHATBOT_REPLY_FALLBACK_OFFER_USUAL, ("products",)),
    "fallback_offer_usual_site": (CHATBOT_REPLY_FALLBACK_OFFER_USUAL_SITE, ("site", "products")),
    "fallback_offer_customer": (CHATBOT_REPLY_FALLBACK_OFFER_CUSTOMER, ("customer", "team")),
    "fallback_noted_role": (CHATBOT_REPLY_FALLBACK_NOTED_ROLE, ("role", "customer")),
    "fallback_noted_role_no_customer": (CHATBOT_REPLY_FALLBACK_NOTED_ROLE_NO_CUSTOMER, ("role",)),
    "fallback_noted_language": (CHATBOT_REPLY_FALLBACK_NOTED_LANGUAGE, ()),
    "fallback_noted": (CHATBOT_REPLY_FALLBACK_NOTED, ()),
    "history_lead": (CHATBOT_REPLY_HISTORY_LEAD, ()),
    "history_offer": (CHATBOT_REPLY_HISTORY_OFFER, ()),
    "history_nothing": (CHATBOT_REPLY_HISTORY_NOTHING, ()),
    "carried_episode": (CHATBOT_REPLY_CARRIED_EPISODE, ("day", "subject")),
    "carried_usual": (CHATBOT_REPLY_CARRIED_USUAL, ("products",)),
    "handover_salesperson": (CHATBOT_REPLY_HANDOVER_SALESPERSON, ("salesperson", "team")),
    "ideation_capture_no_access": (IDEATION_CAPTURE_NO_ACCESS, ()),
    "ideation_capture_unconfigured": (IDEATION_CAPTURE_UNCONFIGURED, ()),
    "ideation_capture_ask_idea": (IDEATION_CAPTURE_ASK_IDEA, ()),
    "ideation_capture_give_up": (IDEATION_CAPTURE_GIVE_UP, ()),
    "ideation_capture_give_up_issue": (IDEATION_CAPTURE_GIVE_UP_ISSUE, ()),
    "ideation_capture_cancelled": (IDEATION_CAPTURE_CANCELLED, ()),
    "ideation_capture_read_failed": (IDEATION_CAPTURE_READ_FAILED, ()),
    "ideation_capture_similar_offered": (IDEATION_CAPTURE_SIMILAR_OFFERED, ()),
    "ideation_capture_similar_offered_reply": (IDEATION_CAPTURE_SIMILAR_OFFERED_REPLY, ()),
    "ideation_capture_similar_offered_see_all": (IDEATION_CAPTURE_SIMILAR_OFFERED_SEE_ALL, ("link",)),
    "ideation_capture_similar_picked": (IDEATION_CAPTURE_SIMILAR_PICKED, ("idea_number", "link")),
    "ideation_capture_similar_picked_no_link": (
        IDEATION_CAPTURE_SIMILAR_PICKED_NO_LINK,
        ("idea_number",),
    ),
    "ideation_capture_complete": (
        IDEATION_CAPTURE_COMPLETE,
        ("idea_number", "title", "missing", "link"),
    ),
    "ideation_capture_complete_no_link": (IDEATION_CAPTURE_COMPLETE_NO_LINK, ("idea_number", "title")),
    "ideation_capture_ask_issue": (IDEATION_CAPTURE_ASK_ISSUE, ()),
    "ideation_capture_complete_issue": (IDEATION_CAPTURE_COMPLETE_ISSUE, ("idea_number", "title")),
    "ideation_capture_complete_issue_photos": (IDEATION_CAPTURE_COMPLETE_ISSUE_PHOTOS, ("count",)),
    "ideation_capture_test_turn": (IDEATION_CAPTURE_TEST_TURN, ()),
    "ideation_capture_account_failed": (IDEATION_CAPTURE_ACCOUNT_FAILED, ()),
    "ideation_capture_type_refused": (IDEATION_CAPTURE_TYPE_REFUSED, ()),
    "ideation_capture_error": (IDEATION_CAPTURE_ERROR, ()),
    "ideation_capture_config_error": (IDEATION_CAPTURE_CONFIG_ERROR, ()),
}

#: The languages the new templates carry (plan 7.2). English is the bare key.
FALLBACK_LANGUAGES: tuple[str, ...] = ("en", "ms", "zh")


def language_suffix(language: str) -> str:
    """`""` for English (the bare key), `".ms"` / `".zh"` otherwise."""
    return "" if language == "en" else f".{language}"

# `short name -> (registry key, template, declared {{tokens}})`. ONE table: the registry
# builds `PROMPT_KEYS` from it, the seed migration seeds from it, and the package's
# `copy.py` resolves against it, so the three can never list different keys (H28's
# lesson, applied to copy instead of to enums).
CHATBOT_REPLY_COPY: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "access_denied": (
        "chatbot_reply_access_denied",
        CHATBOT_REPLY_ACCESS_DENIED,
        ("team",),
    ),
    "offer_hold": (
        "chatbot_reply_offer_hold",
        CHATBOT_REPLY_OFFER_HOLD,
        ("companies",),
    ),
    "offer_hold_no_companies": (
        "chatbot_reply_offer_hold_no_companies",
        CHATBOT_REPLY_OFFER_HOLD_NO_COMPANIES,
        (),
    ),
    "demand_qty": (
        "chatbot_reply_demand_qty",
        CHATBOT_REPLY_DEMAND_QTY,
        (),
    ),
    "not_supported": (
        "chatbot_reply_not_supported",
        CHATBOT_REPLY_NOT_SUPPORTED,
        (),
    ),
    "clarify_menu": (
        "chatbot_reply_clarify_menu",
        CHATBOT_REPLY_CLARIFY_MENU,
        ("user_goal",),
    ),
    "escalate_offer": (
        "chatbot_reply_escalate_offer",
        CHATBOT_REPLY_ESCALATE_OFFER,
        ("team",),
    ),
    "escalate_offer_no_team": (
        "chatbot_reply_escalate_offer_no_team",
        CHATBOT_REPLY_ESCALATE_OFFER_NO_TEAM,
        (),
    ),
    "out_of_scope": (
        "chatbot_reply_out_of_scope",
        CHATBOT_REPLY_OUT_OF_SCOPE,
        ("team",),
    ),
    "out_of_scope_no_team": (
        "chatbot_reply_out_of_scope_no_team",
        CHATBOT_REPLY_OUT_OF_SCOPE_NO_TEAM,
        (),
    ),
    "escalation_declined": (
        "chatbot_reply_escalation_declined",
        CHATBOT_REPLY_ESCALATION_DECLINED,
        (),
    ),
    "offer_declined": (
        "chatbot_reply_offer_declined",
        CHATBOT_REPLY_OFFER_DECLINED,
        (),
    ),
}

for _name, (_texts, _tokens) in FALLBACK_REPLY_COPY.items():
    for _lang in FALLBACK_LANGUAGES:
        _suffix = language_suffix(_lang)
        CHATBOT_REPLY_COPY[f"{_name}{_suffix}"] = (f"chatbot_reply_{_name}{_suffix}", _texts[_lang], _tokens)
