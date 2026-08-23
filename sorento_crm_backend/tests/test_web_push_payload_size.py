"""A web push payload must fit inside the 4096-byte limit the push services enforce.

The sender used to serialise `notification.data` verbatim. SLA notifications carry
`whatsapp_context_vars` in that same dict for the WhatsApp channel's benefit - contact
name, entity number, reason, two due dates, three URLs and the full message body - and
13 pushes were rejected in production with

    binary data passed in the request must be less than 4096 bytes

which is to say: the single most important event, failing on its own payload.

The service worker (`sorento_crm_frontend/public/sw.js`) reads only `title`, `body` and
`data.link`, plus `data.tag` where a caller sets one, so nothing that was in use is lost
by building the payload explicitly instead of passing `data` through.
"""
import json
from types import SimpleNamespace

from app.tasks.notification_tasks import WEB_PUSH_PAYLOAD_LIMIT_BYTES, build_push_payload


def _notification(**kwargs):
    base = {"title": "SLA escalated", "body": "PR-0042 breached tier 1", "data": {}}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_an_oversized_data_blob_still_produces_a_deliverable_payload():
    """The real shape that failed: a fat whatsapp_context_vars dict beside the link."""
    notification = _notification(
        data={
            "link": "/procurement-management/purchase-requests/9f8e7d6c",
            "tracking_id": "9f8e7d6c-1111-2222-3333-444455556666",
            "whatsapp_context_vars": {
                "message": "x" * 6000,
                "reason": "y" * 2000,
                "portal_url": "https://example.test/" + "z" * 500,
            },
        }
    )
    raw = build_push_payload(notification)
    assert len(raw.encode("utf-8")) < WEB_PUSH_PAYLOAD_LIMIT_BYTES
    decoded = json.loads(raw)
    assert decoded["data"]["link"] == "/procurement-management/purchase-requests/9f8e7d6c"
    assert "whatsapp_context_vars" not in decoded["data"]


def test_the_tag_survives_because_the_worker_coalesces_on_it():
    notification = _notification(data={"link": "/x", "tag": "contact-10025904"})
    assert json.loads(build_push_payload(notification))["data"]["tag"] == "contact-10025904"


def test_a_body_long_enough_on_its_own_is_truncated():
    """A link cannot save a payload whose body alone exceeds the limit."""
    notification = _notification(body="w" * 9000, data={"link": "/x"})
    raw = build_push_payload(notification)
    assert len(raw.encode("utf-8")) < WEB_PUSH_PAYLOAD_LIMIT_BYTES
    assert json.loads(raw)["data"]["link"] == "/x", "the link outranks the body text"


def test_multibyte_bodies_are_measured_in_bytes_not_characters():
    """A CJK body is 3 bytes per character; a character-count cap would still overflow."""
    notification = _notification(body="警" * 3000, data={"link": "/x"})
    assert len(build_push_payload(notification).encode("utf-8")) < WEB_PUSH_PAYLOAD_LIMIT_BYTES


def test_missing_body_and_data_are_tolerated():
    raw = build_push_payload(_notification(body=None, data=None))
    decoded = json.loads(raw)
    assert decoded["body"] == ""
    assert decoded["data"] == {}
