"""Tests for ``abyss.web_push``."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch

import pytest

from abyss import web_push


@pytest.fixture
def abyss_home(tmp_path, monkeypatch):
    home = tmp_path / ".abyss"
    home.mkdir()
    monkeypatch.setenv("ABYSS_HOME", str(home))
    # Reset module-level visibility map between tests so leaks from one
    # test do not leak into another.
    web_push._visible_devices.clear()
    return home


# ---------------------------------------------------------------------------
# VAPID keys
# ---------------------------------------------------------------------------


class TestVapidKeys:
    def test_first_call_generates_and_persists(self, abyss_home):
        keys = web_push.load_vapid_keys()
        assert keys.public_key
        # The encoded form is a raw uncompressed point — 65 bytes
        # before base64. base64url of 65 bytes is 87 chars (no
        # padding). We accept anything between 80 and 90 to give the
        # encoding minor wiggle room across library versions.
        assert 80 <= len(keys.public_key) <= 90
        assert "PRIVATE KEY" in keys.private_pem

        # Disk artefact exists, has restrictive mode, and round-trips.
        path = abyss_home / "vapid-keys.json"
        assert path.exists()
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600
        payload = json.loads(path.read_text())
        assert payload["public_key"] == keys.public_key

    def test_subsequent_calls_load_cached_keys(self, abyss_home):
        first = web_push.load_vapid_keys()
        second = web_push.load_vapid_keys()
        assert first.public_key == second.public_key
        assert first.private_pem == second.private_pem

    def test_corrupt_file_regenerates(self, abyss_home):
        (abyss_home / "vapid-keys.json").write_text("not json")
        keys = web_push.load_vapid_keys()
        assert keys.public_key  # regenerated
        # New file has correct shape.
        payload = json.loads((abyss_home / "vapid-keys.json").read_text())
        assert payload["public_key"] == keys.public_key


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_subscription() -> dict[str, Any]:
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "expirationTime": None,
        "keys": {"p256dh": "p256dh-stub", "auth": "auth-stub"},
        "device_id": "device-1",
    }


class TestSubscriptions:
    @pytest.mark.asyncio
    async def test_add_creates_file_and_returns_via_list(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        path = abyss_home / "push-subscriptions.json"
        assert path.exists()
        assert path.stat().st_mode & 0o777 == 0o600

        subs = web_push.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["endpoint"] == fake_subscription["endpoint"]

    @pytest.mark.asyncio
    async def test_add_is_idempotent_per_endpoint(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        # Same endpoint, new keys → upsert.
        updated = {**fake_subscription, "keys": {"p256dh": "new", "auth": "new"}}
        await web_push.add_subscription(updated)
        subs = web_push.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["keys"]["p256dh"] == "new"

    @pytest.mark.asyncio
    async def test_remove(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        await web_push.remove_subscription(fake_subscription["endpoint"])
        assert web_push.list_subscriptions() == []

    @pytest.mark.asyncio
    async def test_add_rejects_without_endpoint(self, abyss_home):
        with pytest.raises(ValueError):
            await web_push.add_subscription({"keys": {}})

    @pytest.mark.asyncio
    async def test_concurrent_writes_do_not_clobber(self, abyss_home, fake_subscription):
        # Eight concurrent adds with distinct endpoints must all land.
        async def add(index: int):
            await web_push.add_subscription(
                {
                    **fake_subscription,
                    "endpoint": f"{fake_subscription['endpoint']}/{index}",
                    "device_id": f"device-{index}",
                }
            )

        await asyncio.gather(*(add(i) for i in range(8)))
        assert len(web_push.list_subscriptions()) == 8


# ---------------------------------------------------------------------------
# Device visibility
# ---------------------------------------------------------------------------


class TestVisibility:
    def test_mark_visible_then_check(self, abyss_home):
        web_push.mark_device_visible("phone-1")
        assert web_push.is_device_visible("phone-1") is True

    def test_unknown_device_invisible(self, abyss_home):
        assert web_push.is_device_visible("ghost") is False

    def test_empty_device_id_invisible(self, abyss_home):
        assert web_push.is_device_visible(None) is False
        assert web_push.is_device_visible("") is False

    def test_mark_hidden_clears(self, abyss_home):
        web_push.mark_device_visible("phone-1")
        web_push.mark_device_hidden("phone-1")
        assert web_push.is_device_visible("phone-1") is False

    def test_ttl_expires(self, abyss_home, monkeypatch):
        web_push.mark_device_visible("phone-1")
        # Fast-forward past the TTL by advancing monotonic.
        future = time.monotonic() + web_push.VISIBILITY_TTL_SECONDS + 1
        monkeypatch.setattr(time, "monotonic", lambda: future)
        assert web_push.is_device_visible("phone-1") is False
        # Subsequent ``is_device_visible`` cleared the stale entry.
        assert "phone-1" not in web_push._visible_devices


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


class TestSendPush:
    @pytest.mark.asyncio
    async def test_no_subscriptions_returns_zero(self, abyss_home):
        with patch("abyss.web_push.webpush") as mock:
            count = await web_push.send_push(title="t", body="b")
        assert count == 0
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_to_every_subscription(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        await web_push.add_subscription(
            {
                **fake_subscription,
                "endpoint": fake_subscription["endpoint"] + "-2",
                "device_id": "device-2",
            }
        )
        with patch("abyss.web_push.webpush") as mock:
            count = await web_push.send_push(
                title="t",
                body="hello",
                bot="alpha",
                session_id="chat_web_abc",
            )
        assert count == 2
        assert mock.call_count == 2
        # Payload includes bot + session_id when supplied.
        body = json.loads(mock.call_args.kwargs["data"])
        assert body["bot"] == "alpha"
        assert body["session_id"] == "chat_web_abc"

    @pytest.mark.asyncio
    async def test_skips_visible_device_by_default(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        web_push.mark_device_visible(fake_subscription["device_id"])
        with patch("abyss.web_push.webpush") as mock:
            count = await web_push.send_push(title="t", body="b")
        assert count == 0
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_visible_off_still_sends(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)
        web_push.mark_device_visible(fake_subscription["device_id"])
        with patch("abyss.web_push.webpush") as mock:
            count = await web_push.send_push(title="t", body="b", skip_visible=False)
        assert count == 1
        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_410_removes_subscription(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)

        class _Response:
            status_code = 410

        def fake_webpush(*args, **kwargs):
            raise web_push.WebPushException("gone", response=_Response())

        with patch("abyss.web_push.webpush", side_effect=fake_webpush):
            count = await web_push.send_push(title="t", body="b")

        assert count == 0
        assert web_push.list_subscriptions() == []

    @pytest.mark.asyncio
    async def test_transient_error_does_not_remove(self, abyss_home, fake_subscription):
        await web_push.add_subscription(fake_subscription)

        class _Response:
            status_code = 502

        def fake_webpush(*args, **kwargs):
            raise web_push.WebPushException("upstream", response=_Response())

        with patch("abyss.web_push.webpush", side_effect=fake_webpush):
            count = await web_push.send_push(title="t", body="b")

        assert count == 0
        # Still there — the push service may recover.
        assert len(web_push.list_subscriptions()) == 1

    @pytest.mark.asyncio
    async def test_skips_subscription_missing_keys(self, abyss_home, fake_subscription):
        broken = {**fake_subscription, "keys": None}
        # Bypass validation by writing directly (the validator would
        # otherwise reject a non-dict keys block at add time).
        web_push._write_subscriptions([broken])
        with patch("abyss.web_push.webpush") as mock:
            count = await web_push.send_push(title="t", body="b")
        assert count == 0
        mock.assert_not_called()
        # The malformed subscription is reaped on the next send.
        assert web_push.list_subscriptions() == []
