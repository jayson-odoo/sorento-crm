"""An admin-editable outbound URL, checked before the CRM will POST to it (AC-804).

The chatbot retry webhook moved off the environment and onto the respond workspace row
(owner ruling, 5 Sep: nothing chatbot-shaped in `.env`, it does not scale past one
tenant). That trade is worth stating plainly: a value that used to be set by whoever
deployed the box is now set by whoever can edit Settings, and the CRM makes a server-side
POST to it. Without a check that is a server-side request forgery primitive - an admin
account (or anything that reaches that route) could point it at `169.254.169.254` and
have the CRM fetch cloud instance credentials for them, or at an internal service that
trusts anything arriving from the CRM's own network.

So the URL is checked in BOTH places, and deliberately not only on save:

* **on save**, so the admin gets the refusal while they are looking at the field;
* **on use**, because save-time validation alone is a TOCTOU window. DNS answers change,
  a row can be written by a script or a restore, and the rule that matters is the one
  applied at the moment the socket opens.

Four rules, each named in the refusal so the message says what to change:

1. `https` only. Plaintext would put the retry key on the wire in clear.
2. The host must not resolve to LOOPBACK. That is how a request reaches a service bound
   to the box itself, including the CRM's own API.
3. The host must not resolve into a PRIVATE or LINK-LOCAL range. Link-local carries the
   cloud metadata endpoint (`169.254.169.254`); the private ranges carry everything else
   on the internal network.
4. The host must not be the CRM ITSELF.

**Every resolved address is checked, not just the first.** A name that answers with one
public address and one private one is the standard way past a check that looks at
`getaddrinfo(...)[0]`.

**What this does NOT do, said out loud.** It cannot close the DNS-rebinding gap: the name
is resolved here and again by the HTTP client, and an attacker who controls the
authoritative server can answer differently the second time. Closing that means resolving
once and connecting to the pinned address with the Host header preserved, which is a
custom transport. The trigger for building it is named rather than guessed: an
untrusted-tenant install, or a second admin-editable outbound URL - today there is one
field, edited by an operator who already has Settings access, and the caller follows no
redirects, so the residual is one DNS round trip wide.

**Documentation ranges (TEST-NET, 192.0.2/24, 198.51.100/24, 203.0.113/24) are allowed.**
`ipaddress.is_private` returns True for them, which is correct about their reservation and
wrong about the risk this guards: they route nowhere internal. Using `is_private` whole
would refuse them for no security gain, so the deny list below is written out.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

# The ranges a webhook must not resolve into. `is_loopback` and `is_link_local` are read
# from `ipaddress` (they are exact and cover both families); these are the private ranges
# that `is_private` would over-match on, written out so the rule is readable.
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        # Carrier-grade NAT. Reachable inside a lot of hosting networks and not public.
        "100.64.0.0/10",
        # "this host on this network" - 0.0.0.0 reaches the local box on Linux.
        "0.0.0.0/8",
        # IPv6 unique-local, the fc00::/7 equivalent of RFC 1918.
        "fc00::/7",
        "::/128",
    )
)


class OutboundUrlRejected(ValueError):
    """The URL breaks one of the four rules. `rule` is the short name of which one.

    A `ValueError` rather than an `HTTPException`, because the two callers answer it
    differently in shape (a save is a form error, a retry is a refused action) and a
    service raising HTTP status codes at a package boundary is what makes a rule like
    this impossible to reuse.
    """

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message


def _resolved_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every address `host` answers with, or the literal when it already is one."""
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise OutboundUrlRejected(
            "unresolvable",
            f"The host {host!r} does not resolve, so the CRM cannot check where a "
            "request to it would go.",
        ) from exc
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        except ValueError:
            continue
        # An IPv4-mapped IPv6 answer (`::ffff:127.0.0.1`) is an IPv4 address wearing a
        # hat, and every range check below is about the address it carries.
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        out.append(address)
    if not out:
        raise OutboundUrlRejected(
            "unresolvable",
            f"The host {host!r} resolved to no usable address.",
        )
    return out


def _own_hostnames() -> set[str]:
    """The names this process answers to.

    Hostname STRINGS, not the addresses they resolve to. Comparing addresses looks
    stricter and is wrong here: the CRM and a legitimate webhook host can sit behind the
    same load-balancer address, and refusing that would block the only URL an operator
    would ever want to enter. The realistic self-reference - `localhost`, `127.0.0.1`, the
    container's own private address - is already refused by rules 2 and 3 above.

    Limitation, named rather than implied: in a container `gethostname()` is the container
    id, not the public API hostname, so this rule catches an operator pasting the machine
    name and not someone pasting the CRM's public URL. The public URL is not knowable from
    here today (there is no configured canonical host); the trigger to add one is the first
    install where the CRM's public hostname is also reachable from inside it.
    """
    names: set[str] = set()
    try:
        own = (socket.gethostname() or "").strip().rstrip(".").lower()
    except OSError:  # pragma: no cover - gethostname does not fail in practice
        return names
    if own:
        names.add(own)
        names.add(own.split(".", 1)[0])
    return names


def assert_safe_outbound_url(url: str, *, label: str = "This URL") -> str:
    """Return the URL, or raise `OutboundUrlRejected` naming the rule it breaks."""
    candidate = (url or "").strip()
    if not candidate:
        raise OutboundUrlRejected("empty", f"{label} is empty.")

    parts = urlsplit(candidate)
    if parts.scheme.lower() != "https":
        raise OutboundUrlRejected(
            "https",
            f"{label} must use https. The retry key travels on this request, and http "
            "would put it on the wire in clear.",
        )
    host = (parts.hostname or "").strip().rstrip(".")
    if not host:
        raise OutboundUrlRejected("host", f"{label} has no host.")

    lowered = host.lower()
    if lowered in _own_hostnames():
        raise OutboundUrlRejected(
            "self",
            f"{label} points at the CRM itself ({host}). A webhook the CRM calls must be "
            "somewhere else, or the CRM would be asking itself to do the work.",
        )

    for address in _resolved_addresses(host):
        if address.is_loopback:
            raise OutboundUrlRejected(
                "loopback",
                f"{label} resolves to a loopback address ({address}). That is this "
                "machine, and a webhook must point somewhere else.",
            )
        if address.is_link_local:
            raise OutboundUrlRejected(
                "link-local",
                f"{label} resolves to a link-local address ({address}). That range "
                "carries the cloud metadata endpoint, so the CRM will not call it.",
            )
        if any(address in network for network in _PRIVATE_NETWORKS):
            raise OutboundUrlRejected(
                "private",
                f"{label} resolves to a private address ({address}). A webhook must be "
                "reachable as a public host, not an address on the internal network.",
            )
    return candidate
