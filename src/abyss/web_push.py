"""VAPID key + subscription management + Web Push delivery.

abyss talks to phones / browsers through the W3C Push API. This
module is the server-side piece:

- Generates and persists the VAPID keypair the first time it is
  asked, so existing browsers can keep their subscriptions across
  restarts.
- Stores Push subscriptions reported by the browser
  (``PushSubscription.toJSON()`` + a device id we mint client-side).
- Tracks which devices currently have the dashboard focused so we
  can skip pushing to them and avoid duplicate notifications.
- Sends a push to every subscription, removing endpoints the push
  service tells us are gone (410 / 404).

The implementation mirrors the proven purplemux pattern (file-backed
JSON, optimistic write + tmp-file rename, in-memory visibility map).

We deliberately do NOT use a database. abyss is single-user,
single-host; a sub-kilobyte JSON file is appropriate and avoids
schema migrations.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from abyss.config import abyss_home

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------


def _vapid_path() -> Path:
    return abyss_home() / "vapid-keys.json"


def _subscriptions_path() -> Path:
    return abyss_home() / "push-subscriptions.json"


# ---------------------------------------------------------------------------
# VAPID key management
# ---------------------------------------------------------------------------


@dataclass
class VapidKeys:
    """Server identity for Web Push.

    ``public_key`` is the base64url-encoded uncompressed P-256 point
    the browser passes back to ``pushManager.subscribe``.
    ``private_pem`` is a PKCS8 PEM ``pywebpush`` will accept.
    """

    public_key: str
    private_pem: str


def _encode_public_key(public_key) -> str:
    """Encode an EC public key as the URL-safe base64 form Web Push expects."""

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _encode_private_key(private_key) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode()


def _generate_keys() -> VapidKeys:
    vapid = Vapid()
    vapid.generate_keys()
    return VapidKeys(
        public_key=_encode_public_key(vapid._public_key),
        private_pem=_encode_private_key(vapid._private_key),
    )


def _atomic_write(path: Path, payload: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, mode)
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def load_vapid_keys() -> VapidKeys:
    """Load the VAPID keypair, generating one on first run.

    The keys file lives in ``~/.abyss/vapid-keys.json`` with mode
    ``0600``. Deleting the file invalidates every existing browser
    subscription — keep a backup.
    """

    path = _vapid_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "public_key" in data and "private_pem" in data:
                return VapidKeys(
                    public_key=data["public_key"],
                    private_pem=data["private_pem"],
                )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("vapid-keys.json unreadable (%s); regenerating", exc)

    keys = _generate_keys()
    _atomic_write(
        path,
        json.dumps(
            {"public_key": keys.public_key, "private_pem": keys.private_pem},
            ensure_ascii=False,
            indent=2,
        ),
    )
    logger.info("Generated new VAPID keypair at %s", path)
    return keys


# ---------------------------------------------------------------------------
# Subscription storage
# ---------------------------------------------------------------------------


_SUBSCRIPTION_LOCK = asyncio.Lock()


def _read_subscriptions() -> list[dict[str, Any]]:
    path = _subscriptions_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict) and "endpoint" in item]
    except (OSError, json.JSONDecodeError) as exc:
        # Surface the read/parse failure in the log so the operator
        # can notice a corrupt subscription file, but keep returning
        # an empty list so a malformed file does not crash every
        # ``send_push`` call. The next ``add_subscription`` writes a
        # fresh atomic snapshot and self-heals.
        logger.warning("push-subscriptions.json unreadable (%s); ignoring", exc)
    return []


def _write_subscriptions(subs: list[dict[str, Any]]) -> None:
    _atomic_write(
        _subscriptions_path(),
        json.dumps(subs, ensure_ascii=False, indent=2),
    )


async def add_subscription(subscription: dict[str, Any]) -> None:
    """Upsert a Push subscription by ``endpoint``.

    Mobile browsers may re-subscribe (e.g. after a re-install) with
    the same ``device_id`` but a new endpoint — we keep both. The
    upsert is keyed on the endpoint because that is what Web Push
    actually delivers to.
    """

    if not isinstance(subscription, dict) or not subscription.get("endpoint"):
        raise ValueError("subscription must be a dict with 'endpoint'")

    async with _SUBSCRIPTION_LOCK:
        subs = _read_subscriptions()
        endpoint = subscription["endpoint"]
        existing = next(
            (index for index, sub in enumerate(subs) if sub.get("endpoint") == endpoint),
            None,
        )
        if existing is not None:
            subs[existing] = subscription
        else:
            subs.append(subscription)
        _write_subscriptions(subs)


async def remove_subscription(endpoint: str) -> None:
    if not endpoint:
        return
    async with _SUBSCRIPTION_LOCK:
        subs = _read_subscriptions()
        filtered = [sub for sub in subs if sub.get("endpoint") != endpoint]
        if len(filtered) != len(subs):
            _write_subscriptions(filtered)


def list_subscriptions() -> list[dict[str, Any]]:
    """Snapshot read. Safe under the GIL for short reads."""

    return _read_subscriptions()


# ---------------------------------------------------------------------------
# Device visibility (in-memory, ~60s TTL)
# ---------------------------------------------------------------------------


# Maps ``device_id`` (a UUID minted client-side in localStorage) to the
# last time we heard "this tab is focused". We refuse to push to a
# device that pinged within ``VISIBILITY_TTL_SECONDS`` so the user
# does not get a notification for content they are already looking at.
_visible_devices: dict[str, float] = {}
VISIBILITY_TTL_SECONDS = 60.0


def mark_device_visible(device_id: str) -> None:
    if not device_id:
        return
    _visible_devices[device_id] = time.monotonic()


def mark_device_hidden(device_id: str) -> None:
    if not device_id:
        return
    _visible_devices.pop(device_id, None)


def is_device_visible(device_id: str | None) -> bool:
    if not device_id:
        return False
    seen_at = _visible_devices.get(device_id)
    if seen_at is None:
        return False
    if time.monotonic() - seen_at > VISIBILITY_TTL_SECONDS:
        # Garbage-collect stale entries opportunistically.
        _visible_devices.pop(device_id, None)
        return False
    return True


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


@dataclass
class PushPayload:
    """JSON shape the Service Worker receives in its ``push`` event.

    Keep this small — the iOS push budget is roughly 4 KB per
    message. Anything heavier (full transcripts, attachments) stays
    on the server; the click handler navigates the user to the live
    dashboard where the data is already available.
    """

    title: str
    body: str
    bot: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"title": self.title, "body": self.body}
        if self.bot:
            out["bot"] = self.bot
        if self.session_id:
            out["session_id"] = self.session_id
        return out


VAPID_CONTACT = os.environ.get("ABYSS_VAPID_CONTACT", "mailto:me@heg.wtf")


def _vapid_private_b64url(private_pem: str) -> str:
    """Return the VAPID private key as base64url-encoded DER bytes.

    ``pywebpush.webpush`` forwards ``vapid_private_key`` into
    ``py_vapid.Vapid.from_string``, which only accepts the
    base64url-encoded raw or DER form — passing the full PEM
    (``-----BEGIN PRIVATE KEY-----...``) makes ``from_string`` run
    ``b64urldecode`` on the PEM headers themselves, yielding garbage
    bytes that fail ASN.1 parsing with
    ``Could not deserialize key data ... invalid length``.

    Load the PEM through ``cryptography`` once and re-export as DER
    so callers can hand a clean string to ``pywebpush``.
    """
    private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    der_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.urlsafe_b64encode(der_bytes).rstrip(b"=").decode("ascii")


async def send_push(
    *,
    title: str,
    body: str,
    bot: str | None = None,
    session_id: str | None = None,
    skip_visible: bool = True,
) -> int:
    """Send a push to every stored subscription.

    Returns the number of successful deliveries (i.e. push service
    returned 2xx). Subscriptions that respond with 404 or 410 are
    auto-removed because the push service has signalled the
    subscription is no longer reachable — keeping them around just
    wastes a network round-trip on every send.

    ``skip_visible`` defaults to True so we do not double-notify a
    user who is actively looking at the dashboard.
    """

    subscriptions = list_subscriptions()
    if not subscriptions:
        return 0

    keys = load_vapid_keys()
    vapid_private = _vapid_private_b64url(keys.private_pem)
    vapid_claims = {"sub": VAPID_CONTACT}
    payload = json.dumps(
        PushPayload(title=title, body=body, bot=bot, session_id=session_id).to_dict(),
        ensure_ascii=False,
    )

    delivered = 0
    expired: list[str] = []

    for sub in subscriptions:
        device_id = sub.get("device_id")
        if skip_visible and is_device_visible(device_id):
            continue
        endpoint = sub.get("endpoint")
        keys_block = sub.get("keys")
        if not endpoint or not isinstance(keys_block, dict):
            expired.append(endpoint or "")
            continue
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={"endpoint": endpoint, "keys": keys_block},
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims=dict(vapid_claims),
            )
            delivered += 1
        except WebPushException as exc:
            response = exc.response
            status = getattr(response, "status_code", None)
            if status in (404, 410):
                expired.append(endpoint)
                logger.info("Push endpoint gone (%s); removing", status)
            else:
                logger.warning("Push delivery failed for %s: %s", endpoint, exc)
        except Exception as exc:  # noqa: BLE001 — broad on purpose; network failures must not crash callers
            logger.warning("Push delivery raised %s for %s", exc, endpoint)

    for endpoint in expired:
        await remove_subscription(endpoint)

    return delivered


__all__ = [
    "VapidKeys",
    "PushPayload",
    "load_vapid_keys",
    "add_subscription",
    "remove_subscription",
    "list_subscriptions",
    "mark_device_visible",
    "mark_device_hidden",
    "is_device_visible",
    "send_push",
    "VISIBILITY_TTL_SECONDS",
]
