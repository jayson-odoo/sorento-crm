"""AGENTIC-WA-S2: a warranty / complaint claim with chat photos on WhatsApp (UAC C-1 .. C-18).

Red tests, written before the complaint tools exist. A contact principal (Agent switch on, no linked active
user) lists its own stored chat photos, proposes a claim through the portal complaint service, confirms it
on its next turn, withdraws it, and adds or removes photos later. Postgres only, blank schema; every test
seeds its own chain. Storage is an in-memory fake: nothing leaves the process.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact

PHOTOS = "crm_my_chat_photos"
CP_CREATE = "crm_complaint_create"
CP_WITHDRAW = "crm_complaint_withdraw"
CP_PHOTOS_ADD = "crm_complaint_photos_add"
CP_PHOTO_REMOVE = "crm_complaint_photo_remove"
S2_TOOLS = {PHOTOS, CP_CREATE, CP_WITHDRAW, CP_PHOTOS_ADD, CP_PHOTO_REMOVE}
SRT = "00000000-0000-0000-0000-000000000001"
SPACE = "zzt-space"
JPEG = b"\xff\xd8\xff\xe0" + b"zzt-photo" * 10


class FakeStore:
    """An in-memory storage backend: upload / download / delete by key."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def upload_file(self, file_content=None, file_path=None, content_type=None, **kw):
        data = file_content if file_content is not None else kw.get("contents")
        self.files[file_path] = data
        return file_path, None

    def download_file(self, key):
        return self.files[key]

    def delete_file(self, key):
        return self.files.pop(key, None) is not None

    def file_exists(self, key):
        return key in self.files

    def get_signed_url(self, key, expires_in=3600):
        return f"signed:{key}"


@pytest.fixture()
def store(monkeypatch):
    from app.services import storage_router

    fake = FakeStore()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: fake)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(storage_router, "cdn_base_url", lambda provider, key: key)
    return fake


@pytest.fixture()
def db(monkeypatch, store):
    from app.services import lookup_validator
    from app.services.chatbot.head import access as head_access

    monkeypatch.setattr(head_access, "default_space_id", lambda _db: SPACE)
    lookup_validator._cache_clear()
    with blank_session() as session:
        _attachment_types(session)
        _lookups(session)
        yield session
    lookup_validator._cache_clear()


@pytest.fixture(autouse=True)
def _listeners():
    from app.audit_context import clear_actor
    from app.services.audit_service import register_audit_listeners
    from app.services.company_scope import register_company_scope_listeners
    from app.services.lookup_write_listener import register_lookup_write_listeners

    register_company_scope_listeners()
    register_audit_listeners()
    register_lookup_write_listeners()
    yield
    clear_actor()


@pytest.fixture(autouse=True)
def _no_outside_calls(monkeypatch):
    """Submits notify teams; nothing may leave the process (no Respond, no email)."""
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)


# ------------------------------------------------------------------ seeds


def _attachment_types(db) -> None:
    from app.models.resources import AttachmentType

    for code, exts, count in (("portal_submission", "jpg,jpeg,png,pdf", 5), ("chatbot_media", "jpg,jpeg,png,ogg", None)):
        if db.query(AttachmentType).filter(AttachmentType.code == code).first() is None:
            db.add(AttachmentType(id=str(uuid.uuid4()), code=code, type_name=unique_code(code), allowed_extensions=exts,
                                  max_file_size_mb=10, max_count_per_entity=count))
    db.flush()


LOOKUPS = {
    "within_warranty": ("complaints_within_warranty", [("yes", "Yes"), ("no", "No"), ("not_sure", "Not sure")], "yes"),
    "complaint_type": ("complaints_complaint_type", [("product_defect", "Product defect"), ("delivery", "Delivery")],
                       "product_defect"),
    "defects_discovered": ("complaints_defects_discovered", [("after_install", "After installation"),
                                                             ("before_install", "Before installation")],
                           "after_install"),
    "customer_type": ("complaints_customer_type", [("dealer", "Dealer"), ("end_user", "End user")], "dealer"),
}


def _lookups(db) -> None:
    from app.models.lookup import LookupBinding, LookupOption, LookupSet

    for column, (key, options, default) in LOOKUPS.items():
        if db.query(LookupSet).filter(LookupSet.set_key == key).first() is not None:
            continue
        s = LookupSet(id=str(uuid.uuid4()), set_key=key, name=key)
        db.add(s)
        db.flush()
        for n, (value, label) in enumerate(options):
            db.add(LookupOption(id=str(uuid.uuid4()), set_id=s.id, value=value, label=label, sort_order=n))
        db.add(LookupBinding(id=str(uuid.uuid4()), set_id=s.id, table_name="complaints", column_name=column,
                             default_value=default))
    db.flush()


def _dealer(db, *, name: str = "ZZT Dealer Tan") -> dict:
    contact = seed_contact(db)
    db.execute(
        text("INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) VALUES (:i, :c, :co)"),
        {"i": str(uuid.uuid4()), "c": contact["pk"], "co": SRT},
    )
    db.execute(text("UPDATE respond_contacts SET name = :n WHERE id = :c"), {"n": name, "c": contact["pk"]})
    contact["phone"] = db.execute(text("SELECT phone_number FROM respond_contacts WHERE id = :c"),
                                  {"c": contact["pk"]}).scalar()
    contact["name"] = name
    db.flush()
    return contact


def _ctx(db, contact):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, contact["respond_id"])


def _hide_form(db, contact_pk: str, kind: str = "complaint") -> None:
    from app.models.price_tag import ContactPortalFormOverride

    db.add(ContactPortalFormOverride(id=str(uuid.uuid4()), contact_id=contact_pk, form_type=kind, is_enabled=False))
    db.flush()


def _order(db, contact_pk: str | None, *, codes=("ELP3754",), debtor: str = "ZZT Debtor Sdn Bhd",
           number: str | None = None) -> str:
    """An order (DO) of a customer; linked to `contact_pk` as its own account unless None. Returns the number."""
    from app.models.access import RespondContactCustomer
    from app.models.base import company_scope
    from app.models.inventory import Warehouse
    from app.models.order import Customer, Order, OrderLine
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    number = number or unique_code("DO")
    with company_scope(db, frozenset({SRT})):
        cust = Customer(id=str(uuid.uuid4()), customer_code=unique_code("300-"), customer_name=debtor, company_id=SRT)
        wh = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("W"), warehouse_name="ZZT WH", company_id=SRT)
        cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("C"), category_name="ZZT cat",
                              search_synonyms=[])
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("U"), uom_name="ZZT uom")
        db.add_all([cust, wh, cat, uom])
        db.flush()
        order = Order(id=str(uuid.uuid4()), order_number=number, customer_id=cust.id, debtor_name=debtor,
                      company_id=SRT, order_date=date.today())
        db.add(order)
        db.flush()
        for n, code in enumerate(codes, 1):
            product = db.query(Product).filter(Product.product_code == code).first()
            if product is None:
                product = Product(id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}",
                                  category_id=cat.id, base_uom_id=uom.id, list_price=1, company_id=SRT)
                db.add(product)
                db.flush()
            db.add(OrderLine(id=str(uuid.uuid4()), order_id=order.id, product_id=product.id, warehouse_id=wh.id,
                             line_sequence=n, quantity=2, company_id=SRT))
        if contact_pk:
            db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=contact_pk, customer_id=cust.id,
                                          company_id=SRT))
        db.flush()
    return number


def _chat_photo(db, store: FakeStore, contact: dict, *, minutes_ago: int = 5, mime: str = "image/jpeg",
                read: dict | None = None, failed: bool = False, data: bytes = JPEG) -> str:
    """A WhatsApp photo the media lane stored for the contact (`media_tasks._store_media_bytes` shape).
    Returns the attachment id."""
    from app.models.media import ContactMediaUsage, MediaExtractionJob
    from app.services.entity_attachment_service import EntityAttachmentService

    stamp = datetime.utcnow() - timedelta(minutes=minutes_ago)
    turn_id = str(uuid.uuid4())
    modality = "voice" if mime.startswith("audio") else "image"
    usage = ContactMediaUsage(id=str(uuid.uuid4()), respond_io_id=contact["respond_id"], contact_id=contact["pk"],
                              modality=modality, message_id=unique_code("m"), period_key=stamp.strftime("%Y-%m"),
                              outcome="accepted", turn_id=turn_id, created_at=stamp)
    db.add(usage)
    db.flush()
    result = None if failed else (read or {"image_kind": "product", "entities": [{"raw": "ELP3754"}],
                                           "notes": "water stain under the basin", "attributes": []})
    db.add(MediaExtractionJob(id=str(uuid.uuid4()), usage_id=usage.id, status="failed" if failed else "completed",
                              modality=modality, mime_type=mime, result=result, created_at=stamp))
    ext = {"image/jpeg": "jpg", "image/png": "png", "audio/ogg": "ogg"}.get(mime, "jpg")
    key = f"chatbot-media/{usage.id}-{uuid.uuid4().hex}.{ext}"
    store.files[key] = data
    link = EntityAttachmentService(db).create_attachment_and_link(
        entity_type="chatbot_turn", entity_id=turn_id, file_url=key, file_name=key.rsplit("/", 1)[-1],
        file_size_bytes=len(data), attachment_type_code="chatbot_media", storage_provider="s3", mime_type=mime,
        uploader_kind="contact", uploaded_by_contact_id=contact["pk"],
    )
    db.execute(text("UPDATE attachments SET created_at = :t, uploaded_at = :t WHERE id = :i"),
               {"t": stamp, "i": link.attachment_id})
    db.flush()
    return str(link.attachment_id)


def _read_photos(db, ctx, seen: set[str] | None = None) -> dict:
    from app.services.chatbot.agent import portal_writes

    seen = set() if seen is None else seen
    out = portal_writes.run_read(db, ctx, PHOTOS, {}, seen)
    assert out.status == "ok", out.message
    return out.data


def _claim(do: str, **over) -> dict:
    args = {
        "delivery_order_numbers": [do],
        "product_codes": ["ELP3754"],
        "defect_description": "leaking after 3 months",
        "within_warranty": "Yes",
    }
    args.update(over)
    return {k: v for k, v in args.items() if v is not None}


def _propose(db, ctx, name, args, seen=(), *, is_test=False):
    from app.services.chatbot.agent import writes

    return writes.propose_step(db, ctx, name, args, seen_ids=set(seen), loop_args={"_is_test": is_test})


def _store_and_confirm(db, ctx, step, *, operator: str | None = None):
    from app.services.chatbot.agent import actions

    action = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])
    if operator:
        return actions.confirm(db, ctx.contact_respond_id, str(action.id), via="console", operator_user_id=operator)
    return actions.confirm(db, ctx.contact_respond_id, str(action.id), via="chat", turn_id=str(uuid.uuid4()))


def _complaints(db, contact_pk: str) -> list:
    from app.models.complaints import Complaint

    return db.query(Complaint).filter(Complaint.contact_id == contact_pk).all()


def _files_on(db, kind: str, entity_id: str) -> list:
    from app.models.entity_attachment import EntityAttachmentLink

    return db.query(EntityAttachmentLink).filter(
        EntityAttachmentLink.entity_type == kind, EntityAttachmentLink.entity_id == str(entity_id)
    ).all()


def _submitted_complaint(db, contact: dict, *, do: str, minutes_ago: int = 1, history: int = 1, **cols) -> str:
    """A submitted complaint of the contact with `history` revision rows, submitted `minutes_ago`."""
    from app.models.complaints import Complaint, ComplaintProductLine
    from app.models.portal import PortalFormRevision

    cid = str(uuid.uuid4())
    values = dict(
        id=cid, complaint_number=unique_code("CMP"), status="submitted", contact_id=contact["pk"], space_id=SPACE,
        delivery_order_number=do, product_code="ELP3754", within_warranty="yes", complaint_type="product_defect",
        defects_discovered="after_install", customer_type="dealer", defect_description="earlier claim",
        customer_name="ZZT Debtor Sdn Bhd", contact_person="ZZT", contact_number="1", salesperson="ZZT",
        complaint_date=date.today(),
    )
    values.update(cols)
    db.add(Complaint(**values))
    db.flush()
    db.add(ComplaintProductLine(id=str(uuid.uuid4()), complaint_id=cid, product_code="ELP3754", quantity="1"))
    stamp = datetime.utcnow() - timedelta(minutes=minutes_ago)
    for n in range(1, history + 1):
        db.add(PortalFormRevision(
            id=str(uuid.uuid4()), source_entity_type="complaint", source_entity_id=cid, version_no=n,
            revision_no=0, kind="original" if n == 1 else "resubmission", created_at=stamp, submitted_at=stamp,
        ))
    db.flush()
    return cid


def _claim_step(db, store, contact, *, photos: int = 0, **over):
    """A proposed claim on the dealer's own DO with `photos` chat photos."""
    ctx = _ctx(db, contact)
    do = _order(db, contact["pk"])
    ids = [_chat_photo(db, store, contact, minutes_ago=10 - n) for n in range(photos)]
    seen: set[str] = set()
    if ids:
        _read_photos(db, ctx, seen)
    out, step = _propose(db, ctx, CP_CREATE, _claim(do, photo_ids=ids or None, **over), seen)
    assert step is not None, out.message
    return ctx, do, ids, step


# ================================================================ C-1, C-2 exposure


def test_c1_a_dealer_with_the_complaint_form_is_offered_the_five_complaint_tools(db):
    from app.services.chatbot.agent import portal_writes

    offered = set(portal_writes.offered(db, _ctx(db, _dealer(db))))

    assert S2_TOOLS <= offered
    assert {"crm_my_requests_list", "crm_stock_inquiry_create"} <= offered


def test_c1_a_hidden_complaint_form_drops_all_five(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    _hide_form(db, contact["pk"])
    offered = set(portal_writes.offered(db, _ctx(db, contact)))

    assert not (S2_TOOLS & offered)
    assert "crm_stock_inquiry_create" in offered


def test_c2_every_complaint_tool_has_a_router_label():
    from app.services.chatbot.agent.tools import TOOL_LABELS

    assert S2_TOOLS <= set(TOOL_LABELS)


def test_c2_the_router_lists_the_claim_label_only_when_offered(db):
    from app.services.chatbot import router
    from app.services.chatbot.agent.tools import TOOL_LABELS

    contact = _dealer(db)
    assert TOOL_LABELS[CP_CREATE] in router.agent_tool_labels(db, None, contact_respond_id=contact["respond_id"])
    _hide_form(db, contact["pk"])
    assert TOOL_LABELS[CP_CREATE] not in router.agent_tool_labels(db, None, contact_respond_id=contact["respond_id"])


# ================================================================ C-3 chat photos


def test_c3_the_read_lists_own_recent_photos_newest_first_with_what_they_show(db, store):
    contact = _dealer(db)
    other = _dealer(db, name="ZZT Other")
    older = _chat_photo(db, store, contact, minutes_ago=30)
    newer = _chat_photo(db, store, contact, minutes_ago=2, failed=True)
    _chat_photo(db, store, other, minutes_ago=1)
    _chat_photo(db, store, contact, minutes_ago=60 * 25)
    _chat_photo(db, store, contact, minutes_ago=3, mime="audio/ogg")

    photos = _read_photos(db, _ctx(db, contact))["photos"]

    assert [p["id"] for p in photos] == [newer, older]
    assert photos[0]["shows"] == "could not be read"
    assert "ELP3754" in photos[1]["shows"]
    assert photos[1]["sent"]


def test_c3_the_read_returns_at_most_ten(db, store):
    contact = _dealer(db)
    for n in range(12):
        _chat_photo(db, store, contact, minutes_ago=n + 1)

    assert len(_read_photos(db, _ctx(db, contact))["photos"]) == 10


# ================================================================ C-4 .. C-11 propose


def test_c10_a_valid_claim_reads_every_value_and_photo_and_writes_nothing(db, store):
    contact = _dealer(db)
    ctx = _ctx(db, contact)
    do = _order(db, contact["pk"])
    read = _chat_photo(db, store, contact, minutes_ago=8)
    unread = _chat_photo(db, store, contact, minutes_ago=6, failed=True)
    seen: set[str] = set()
    _read_photos(db, ctx, seen)

    out, step = _propose(db, ctx, CP_CREATE, _claim(do, photo_ids=[read, unread]), seen)

    assert step is not None, out.message
    summary = step["summary"]
    for part in (do, "ELP3754", '"leaking after 3 months"', "within warranty: Yes", "Product defect",
                 "After installation", "Dealer", "ZZT Debtor Sdn Bhd", contact["name"], contact["phone"],
                 "could not be read", "water stain"):
        assert part in summary, (part, summary)
    assert summary.count("photo") >= 2
    assert _complaints(db, contact["pk"]) == []


def test_c4_within_warranty_is_never_defaulted(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do, within_warranty=None))

    assert step is None
    assert out.status == "invalid" and "within_warranty" in out.message


def test_c5_another_dealers_do_is_not_found_and_names_no_customer(db, store):
    contact = _dealer(db)
    foreign = _order(db, None, debtor="ZZT Secret Rival Sdn Bhd")

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(foreign))

    assert step is None
    assert f"Delivery order {foreign} not found" in out.message
    assert "Rival" not in out.message
    assert _complaints(db, contact["pk"]) == []


def test_c5_a_partial_do_number_is_not_found(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do[:-2]))

    assert step is None and "not found" in out.message


def test_c5_the_do_matches_ignoring_case_and_spaces(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(f"  {do.lower()} "))

    assert step is not None, out.message


def test_c6_a_product_not_on_the_do_is_refused(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])
    _order(db, contact["pk"], codes=("CB1506SS",))

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do, product_codes=["CB1506SS"]))

    assert step is None and "CB1506SS" in out.message


def test_c7_a_wrong_lookup_value_is_refused_with_its_options(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do, complaint_type="angry customer"))

    assert step is None
    assert "Product defect" in out.message and "Delivery" in out.message


def test_c7_an_omitted_lookup_with_no_default_is_asked_for(db, store):
    from app.models.lookup import LookupBinding, LookupSet
    from app.services import lookup_validator

    s = db.query(LookupSet).filter(LookupSet.set_key == "complaints_complaint_type").one()
    db.query(LookupBinding).filter(LookupBinding.set_id == s.id).update({"default_value": None})
    db.flush()
    lookup_validator._cache_clear()
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do))

    assert step is None and "complaint_type" in out.message


def test_c8_a_site_contact_named_by_the_dealer_replaces_the_default(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), CP_CREATE,
                         _claim(do, contact_person="Encik Ali", contact_number="0123456789"))

    assert step is not None, out.message
    assert "Encik Ali" in step["summary"] and "0123456789" in step["summary"]


def test_c9_a_photo_id_not_read_this_turn_is_refused(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])
    pid = _chat_photo(db, store, contact)

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do, photo_ids=[pid]))

    assert step is None and out.status == "invalid"


def test_c9_another_contacts_photo_is_refused(db, store):
    contact = _dealer(db)
    other = _dealer(db, name="ZZT Other")
    do = _order(db, contact["pk"])
    theirs = _chat_photo(db, store, other)

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do, photo_ids=[theirs]), {theirs})

    assert step is None and "not found" in out.message.lower()


def test_c9_more_photos_than_the_portal_allows_are_refused(db, store):
    contact = _dealer(db)
    ctx = _ctx(db, contact)
    do = _order(db, contact["pk"])
    ids = [_chat_photo(db, store, contact, minutes_ago=n + 1) for n in range(6)]
    seen: set[str] = set()
    _read_photos(db, ctx, seen)

    out, step = _propose(db, ctx, CP_CREATE, _claim(do, photo_ids=ids), seen)

    assert step is None and "Attachment limit reached (5)" in out.message


def test_c11_duplicates_are_allowed_by_default_and_the_earlier_claim_is_named(db, store):
    contact = _dealer(db)
    do = _order(db, contact["pk"])
    earlier = _submitted_complaint(db, contact, do=do, minutes_ago=60 * 24)
    from app.models.complaints import Complaint

    number = db.get(Complaint, earlier).complaint_number
    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do))

    assert step is not None, out.message
    assert number in step["summary"]


def test_c11_the_refuse_switch_refuses_a_duplicate_with_the_note_offer(db, store, monkeypatch):
    from app.services.chatbot.agent import portal_writes

    monkeypatch.setattr(portal_writes, "DUPLICATE_CLAIMS", "refuse")
    contact = _dealer(db)
    do = _order(db, contact["pk"])
    _submitted_complaint(db, contact, do=do, minutes_ago=60 * 24)

    out, step = _propose(db, _ctx(db, contact), CP_CREATE, _claim(do))

    assert step is None and "I can add a note to it instead" in out.message


# ================================================================ C-12 .. C-14 confirm


def test_c12_a_confirm_files_the_claim_with_its_photos_through_the_portal(db, store):
    from app.models.portal import PortalFormRevision
    from app.models.resources import Attachment

    contact = _dealer(db)
    ctx, do, ids, step = _claim_step(db, store, contact, photos=2, defect_description="水龙头漏水, 3个月")

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    [row] = _complaints(db, contact["pk"])
    assert row.status == "submitted" and row.portal_draft_at is None and row.complaint_number
    assert row.delivery_order_number == do and row.product_code == "ELP3754"
    assert row.defect_description == "水龙头漏水, 3个月"
    assert row.within_warranty == "yes" and row.complaint_type == "product_defect"
    assert row.customer_name == "ZZT Debtor Sdn Bhd"
    assert row.contact_person == contact["name"] and row.contact_number == contact["phone"]
    assert row.salesperson == contact["name"] and row.complaint_date == date.today()
    links = _files_on(db, "complaint", row.id)
    assert len(links) == 2
    for link in links:
        att = db.get(Attachment, link.attachment_id)
        assert att.uploaded_by_contact_id == contact["pk"] and att.uploader_kind == "contact"
        assert att.file_path.startswith(f"portal/{contact['pk']}/")
        assert store.files[att.file_path] == JPEG
    assert db.query(PortalFormRevision).filter(PortalFormRevision.source_entity_id == str(row.id)).count() == 1
    assert outcome.notes == [f"Complaint {row.complaint_number} is with the team. Reply undo within 10 minutes to withdraw it."]


def test_c13_a_refused_submit_leaves_no_draft_and_no_file(db, store, monkeypatch):
    from app.services.error_handler import handle_validation_error
    from app.services.portal_service import PortalService

    contact = _dealer(db)
    ctx, _do, _ids, step = _claim_step(db, store, contact, photos=1)
    before = set(store.files)

    def refuse(self, *a, **k):
        raise handle_validation_error("Refused for the test.")

    monkeypatch.setattr(PortalService, "submit_draft", refuse)
    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "partial"
    assert _complaints(db, contact["pk"]) == []
    assert set(store.files) == before


def test_c14_a_console_confirm_writes_nothing(db, store):
    from tests.chatbot.agent._seed import seed_user

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    do = _order(db, contact["pk"])
    operator = seed_user(db, contact_pk=None, slugs=())
    out, step = _propose(db, ctx, CP_CREATE, _claim(do), is_test=True)
    assert step is not None, out.message

    outcome = _store_and_confirm(db, ctx, step, operator=operator)

    assert outcome.status == "executed"
    assert _complaints(db, contact["pk"]) == []
    assert "Test turn: nothing was sent." in outcome.reply_text


# ================================================================ C-15 withdraw


def test_c15_a_fresh_untouched_claim_is_withdrawn_with_its_files(db, store):
    contact = _dealer(db)
    ctx, _do, _ids, step = _claim_step(db, store, contact, photos=1)
    assert _store_and_confirm(db, ctx, step).status == "executed"
    [row] = _complaints(db, contact["pk"])
    cid = str(row.id)
    seen = {cid}

    out, wstep = _propose(db, ctx, CP_WITHDRAW, {"submission_id": cid}, seen)
    assert wstep is not None, out.message
    outcome = _store_and_confirm(db, ctx, wstep)

    assert outcome.status == "executed", outcome.reply_text
    db.expire_all()
    assert _complaints(db, contact["pk"]) == []
    assert _files_on(db, "complaint", cid) == []
    assert not any(k.startswith(f"portal/{contact['pk']}/") for k in store.files)


@pytest.mark.parametrize("cols", [
    {"technical_team_response": "We will send a technician."},
    {"resolved_at": datetime.utcnow()},
    {"status": "in_progress"},
])
def test_c15_a_touched_claim_is_not_withdrawn(db, store, cols):
    from app.services.chatbot.agent.portal_writes import WITHDRAW_REFUSED

    contact = _dealer(db)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]), **cols)

    out, step = _propose(db, _ctx(db, contact), CP_WITHDRAW, {"submission_id": cid}, {cid})

    assert step is None and WITHDRAW_REFUSED in out.message


def test_c15_an_old_claim_is_not_withdrawn(db, store):
    from app.services.chatbot.agent.portal_writes import WITHDRAW_REFUSED

    contact = _dealer(db)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]), minutes_ago=11)

    out, step = _propose(db, _ctx(db, contact), CP_WITHDRAW, {"submission_id": cid}, {cid})

    assert step is None and WITHDRAW_REFUSED in out.message


def test_c15_a_claim_with_a_staff_file_is_not_withdrawn(db, store):
    from app.services.chatbot.agent.portal_writes import WITHDRAW_REFUSED
    from app.services.entity_attachment_service import EntityAttachmentService

    contact = _dealer(db)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]))
    EntityAttachmentService(db).create_attachment_and_link(
        entity_type="complaint", entity_id=cid, file_url="staff/x.jpg", attachment_type_code="portal_submission",
        uploader_kind="user", mime_type="image/jpeg",
    )
    db.flush()

    out, step = _propose(db, _ctx(db, contact), CP_WITHDRAW, {"submission_id": cid}, {cid})

    assert step is None and WITHDRAW_REFUSED in out.message


def test_c15_another_contacts_claim_is_not_found(db, store):
    contact = _dealer(db)
    other = _dealer(db, name="ZZT Other")
    cid = _submitted_complaint(db, other, do=_order(db, other["pk"]))

    out, step = _propose(db, _ctx(db, contact), CP_WITHDRAW, {"submission_id": cid}, {cid})

    assert step is None and "not found" in out.message.lower()


# ================================================================ C-16, C-17 later photos


def test_c16_newer_photos_are_added_to_an_own_open_claim(db, store):
    contact = _dealer(db)
    ctx = _ctx(db, contact)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]), minutes_ago=30)
    pid = _chat_photo(db, store, contact, minutes_ago=2)
    seen = {cid}
    _read_photos(db, ctx, seen)

    out, step = _propose(db, ctx, CP_PHOTOS_ADD, {"submission_id": cid, "photo_ids": [pid]}, seen)
    assert step is not None, out.message
    assert "ELP3754" in step["summary"]
    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    assert len(_files_on(db, "complaint", cid)) == 1

    out, again = _propose(db, ctx, CP_PHOTOS_ADD, {"submission_id": cid, "photo_ids": [pid]}, seen)
    assert again is None and "already" in out.message


def test_c16_photos_on_another_contacts_claim_are_not_found(db, store):
    contact = _dealer(db)
    other = _dealer(db, name="ZZT Other")
    ctx = _ctx(db, contact)
    cid = _submitted_complaint(db, other, do=_order(db, other["pk"]))
    pid = _chat_photo(db, store, contact)
    seen = {cid}
    _read_photos(db, ctx, seen)

    out, step = _propose(db, ctx, CP_PHOTOS_ADD, {"submission_id": cid, "photo_ids": [pid]}, seen)

    assert step is None and "not found" in out.message.lower()


def test_c16_a_resolved_claim_takes_no_more_photos(db, store):
    contact = _dealer(db)
    ctx = _ctx(db, contact)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]), status="resolved",
                               resolved_at=datetime.utcnow())
    pid = _chat_photo(db, store, contact)
    seen = {cid}
    _read_photos(db, ctx, seen)

    out, step = _propose(db, ctx, CP_PHOTOS_ADD, {"submission_id": cid, "photo_ids": [pid]}, seen)

    assert step is None


def test_c17_the_dealer_removes_its_own_photo_but_not_a_staff_file(db, store):
    from app.services.entity_attachment_service import EntityAttachmentService

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    cid = _submitted_complaint(db, contact, do=_order(db, contact["pk"]), minutes_ago=30)
    pid = _chat_photo(db, store, contact)
    seen = {cid}
    _read_photos(db, ctx, seen)
    _out, step = _propose(db, ctx, CP_PHOTOS_ADD, {"submission_id": cid, "photo_ids": [pid]}, seen)
    assert _store_and_confirm(db, ctx, step).status == "executed"
    [own] = _files_on(db, "complaint", cid)
    staff = EntityAttachmentService(db).create_attachment_and_link(
        entity_type="complaint", entity_id=cid, file_url="staff/y.jpg", attachment_type_code="portal_submission",
        uploader_kind="user", mime_type="image/jpeg",
    )
    db.flush()
    seen |= {str(own.id), str(staff.id)}

    out, refused = _propose(db, ctx, CP_PHOTO_REMOVE, {"submission_id": cid, "file_id": str(staff.id)}, seen)
    assert refused is None

    out, step = _propose(db, ctx, CP_PHOTO_REMOVE, {"submission_id": cid, "file_id": str(own.id)}, seen)
    assert step is not None, out.message
    assert _store_and_confirm(db, ctx, step).status == "executed"
    assert [str(l.id) for l in _files_on(db, "complaint", cid)] == [str(staff.id)]


# ================================================================ C-18 photo kept on a failed read


def test_c18_a_failed_read_still_carries_the_fetched_image(monkeypatch):
    from app.services.media_extract import service as media_service

    class Boom:
        def chat(self, **kw):
            raise RuntimeError("provider down")

    monkeypatch.setattr(media_service, "fetch_media_bytes", lambda url: (JPEG, "image/jpeg"))
    monkeypatch.setattr(media_service.MediaExtractService, "_resolve_image_provider",
                        lambda self, tier, settings: (Boom(), "zzt", "zzt-model"))

    class Settings:
        max_entities = 5

    job = media_service.MediaJobInput(job_id=str(uuid.uuid4()), modality="image", tier=None, media_url="https://x/y",
                                      mime_type="image/jpeg", caption=None, usage_id=None)
    with pytest.raises(media_service.MediaExtractionError) as err:
        media_service.MediaExtractService(db=None)._extract_image(job, Settings())

    assert err.value.media_bytes == JPEG


def test_c18_the_worker_stores_the_photo_of_a_failed_read(db, monkeypatch):
    from app.models.media import ContactMediaUsage, MediaExtractionJob
    from app.services.media_extract.service import MediaExtractionError
    from app.tasks import media_tasks

    contact = _dealer(db)
    usage = ContactMediaUsage(id=str(uuid.uuid4()), respond_io_id=contact["respond_id"], contact_id=contact["pk"],
                              modality="image", message_id=unique_code("m"), period_key="2026-11",
                              outcome="accepted", turn_id=str(uuid.uuid4()))
    db.add(usage)
    db.flush()
    job = MediaExtractionJob(id=str(uuid.uuid4()), usage_id=usage.id, status="queued", modality="image",
                             mime_type="image/jpeg", media_url="https://x/y")
    db.add(job)
    db.commit()

    def failing(_job):
        exc = MediaExtractionError("The vision model call failed: provider down")
        exc.media_bytes, exc.media_content_type = JPEG, "image/jpeg"
        raise exc

    class Session:
        """The test's session, minus close (the worker closes its own)."""

        def __getattr__(self, name):
            return getattr(db, name)

        def close(self):
            pass

    monkeypatch.setattr(media_tasks, "SessionLocal", lambda: Session())
    monkeypatch.setattr(media_tasks, "run_media_extraction", failing)
    monkeypatch.setattr(media_tasks, "deliver_callback", lambda job: None)

    media_tasks.process_media_extraction(str(job.id))

    db.expire_all()
    assert db.get(MediaExtractionJob, job.id).status == "failed"
    assert len(_files_on(db, "chatbot_turn", usage.turn_id)) == 1


# ================================================================ a whole WhatsApp exchange through the agent loop


def _scripted(*results):
    class Provider:
        def __init__(self):
            self.calls = []

        def chat(self, messages, *, tools=None, **kw):
            self.calls.append({"messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools or []]})
            return results[min(len(self.calls), len(results)) - 1]

    return Provider()


def _asks(*calls):
    from app.services.llm_provider import ChatResult

    return ChatResult(content="", prompt_tokens=10, completion_tokens=1, total_tokens=11, tool_calls=list(calls))


def _says(text_):
    return _asks({"id": "ans", "name": "answer", "arguments": {"text": text_, "figures": [], "not_found": [], "not_checked": []}})


def _forbidden(name, args):
    raise AssertionError(f"the MCP must not be reached for {name}")


def test_a_whole_whatsapp_claim_reads_photos_proposes_then_files_on_yes(db, store, capsys):
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = _dealer(db)
    do = _order(db, contact["pk"])
    p1 = _chat_photo(db, store, contact, minutes_ago=4)
    p2 = _chat_photo(db, store, contact, minutes_ago=3, failed=True)
    first = _scripted(
        _asks({"id": "r1", "name": PHOTOS, "arguments": {}}),
        _asks({"id": "p1", "name": CP_CREATE, "arguments": _claim(do, photo_ids=[p1, p2])}),
        _says("I will file this claim when you confirm."),
    )
    turn1 = run_agent_turn(db, contact_respond_id=contact["respond_id"],
                           text=f"ELP3754 from {do} leaking after 3 months, still under warranty, photos above",
                           provider=first, mcp_call=_forbidden, catalog={}, is_test=False)

    assert {PHOTOS, CP_CREATE} <= set(first.calls[0]["tools"])
    assert "WARRANTY CLAIMS" in first.calls[0]["messages"][0]["content"]
    assert turn1.pending_action is not None, turn1.reply_text
    assert "File a warranty / complaint claim" in turn1.reply_text and "could not be read" in turn1.reply_text
    assert _complaints(db, contact["pk"]) == []

    second = _scripted(
        _asks({"id": "c1", "name": "confirm_action", "arguments": {"action_id": turn1.pending_action["id"]}}),
        _says("Filed."),
    )
    turn2 = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="yes", provider=second,
                           mcp_call=_forbidden, catalog={}, is_test=False)

    [row] = _complaints(db, contact["pk"])
    assert row.complaint_number in turn2.reply_text
    assert len(_files_on(db, "complaint", row.id)) == 2
    with capsys.disabled():
        print("\n--- turn 1 reply ---\n" + turn1.reply_text + "\n--- turn 2 reply ---\n" + turn2.reply_text)
