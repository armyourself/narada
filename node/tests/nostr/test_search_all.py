"""Tests for the cross-account search and local directory endpoints.

Everything runs offline: IMAP and Nostr are replaced by in-process fakes
so the endpoints' merging, filtering and degradation logic is exercised
without sockets or credentials.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.modules.openmail.types import Email, Mailbox
from src.nostr.adapter import NostrAdapter
from src.nostr.config import NostrConfig
from src.nostr.identity import generate_nostr_identity
from src.nostr.relay import RelayPool


# ── fakes ────────────────────────────────────────────────────────────────


def _email(
    *,
    sender: str = "Sender <sender@example.com>",
    date: str = "Mon, 01 Jan 2024 10:00:00 +0000",
    subject: str = "Hello",
    body: str = "World",
) -> Email:
    return Email(
        message_id="<m1@example.com>",
        uid="1",
        sender=sender,
        receivers="receiver@example.com",
        date=date,
        subject=subject,
        body=body,
        source="imap",
    )


class FakeIMAP:
    def __init__(self, emails: list[Email], boom: bool = False):
        self._emails = emails
        self._boom = boom
        self.calls: list[tuple] = []

    def search_emails(self, folder, criteria):
        if self._boom:
            raise OSError("connection lost")
        self.calls.append((folder, criteria))
        return []

    def get_emails(self, offset_start, offset_end):
        if self._boom:
            raise OSError("connection lost")
        return Mailbox(
            folder="INBOX",
            emails=self._emails[:offset_end],
            total=len(self._emails),
        )


class FakeClient:
    def __init__(self, emails: list[Email], boom: bool = False):
        self.imap = FakeIMAP(emails, boom=boom)


class FakeClientHandler:
    def __init__(self, clients: dict[str, FakeClient] | None = None):
        self._clients = clients or {}

    def get_clients(self) -> dict:
        return dict(self._clients)

    def is_client_exists(self, account, for_new_messages=False) -> bool:
        return account in self._clients

    def is_connection_available(self, account, for_new_messages=False):
        if account not in self._clients:
            return False
        return not getattr(self._clients[account].imap, "_boom", False)

    def get_client(self, account, for_new_messages=False) -> FakeClient:
        return self._clients[account]


class FakeNostrHandler:
    def __init__(self, adapters: dict[str, NostrAdapter] | None = None):
        self._adapters = adapters or {}

    def get_all_adapters(self) -> dict:
        return dict(self._adapters)

    def get_adapter(self, account):
        return self._adapters.get(account)


def _adapter_with_records(
    account: str,
    records: list[dict],
    *,
    tmp_path: Path,
    identity=None,
) -> NostrAdapter:
    adapter = NostrAdapter(
        account,
        identity=identity,
        config=NostrConfig(relay_urls=[]),
        relay_pool=RelayPool(relay_urls=[]),
        data_dir=tmp_path / account,
    )
    adapter.fetch_records = lambda *, limit=5000: records[:limit]  # type: ignore[method-assign]
    return adapter


def _record(
    *,
    sender: str = "Sender <sender@example.com>",
    to: list[str] | None = None,
    cc: list[str] | None = None,
    date: str = "Mon, 01 Jan 2024 10:00:00 +0000",
    subject: str = "Hello",
    body: str = "World",
) -> dict:
    return {
        "uid": "evt1",
        "source": "nostr",
        "sender": sender,
        "receivers": ", ".join(to or ["me@example.com"]),
        "to": to or ["me@example.com"],
        "cc": cc or [],
        "date": date,
        "subject": subject,
        "body": body,
        "flags": ["\\Seen"],
        "message_id": "<evt1@nostr>",
    }


# ── POST /search-all ─────────────────────────────────────────────────────


class TestSearchAll:
    @pytest.fixture()
    def mailbox_tasks(self, tmp_path, monkeypatch):
        import src.routers.mailbox_tasks as module

        monkeypatch.setattr(module, "client_handler", FakeClientHandler())
        monkeypatch.setattr(module, "nostr_handler", FakeNostrHandler())
        return module

    def _run(self, module, **kwargs):
        from src.routers.mailbox_tasks import SearchAllRequest

        return asyncio.run(module.search_all(SearchAllRequest(**kwargs)))

    def test_returns_nostr_results_tagged_with_account(
        self, mailbox_tasks, tmp_path
    ):
        adapter = _adapter_with_records(
            "alice@example.com",
            [_record(subject="Nostr news", date="2024-01-02T00:00:00Z")],
            tmp_path=tmp_path,
        )
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(mailbox_tasks, query="news")
        assert response.success
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["account"] == "alice@example.com"
        assert results[0]["route"] == "relay"
        assert results[0]["source"] == "nostr"

    def test_query_filters_nostr_records(self, mailbox_tasks, tmp_path):
        adapter = _adapter_with_records(
            "alice@example.com",
            [
                _record(subject="Invoice", body="pay me", date="2024-01-03"),
                _record(subject="Vacation", body="beach", date="2024-01-01"),
            ],
            tmp_path=tmp_path,
        )
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(mailbox_tasks, query="invoice")
        assert response.success
        assert [r["subject"] for r in response.data["results"]] == ["Invoice"]

    def test_imap_results_are_included_and_routed(
        self, mailbox_tasks
    ):
        mailbox_tasks.client_handler = FakeClientHandler(
            {
                "bob@example.com": FakeClient(
                    [_email(subject="From IMAP", date="2024-01-05")]
                )
            }
        )

        response = self._run(mailbox_tasks, query="")
        assert response.success
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["account"] == "bob@example.com"
        assert results[0]["route"] == "gateway"
        assert "bob@example.com" in response.data["accounts"]

    def test_results_sorted_newest_first_across_transports(
        self, mailbox_tasks, tmp_path
    ):
        mailbox_tasks.client_handler = FakeClientHandler(
            {"bob@example.com": FakeClient([_email(date="2024-01-01")])}
        )
        adapter = _adapter_with_records(
            "alice@example.com",
            [_record(date="2024-01-09T00:00:00Z")],
            tmp_path=tmp_path,
        )
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(mailbox_tasks, query="")
        accounts = [r["account"] for r in response.data["results"]]
        assert accounts == ["alice@example.com", "bob@example.com"]

    def test_limit_caps_results(self, mailbox_tasks, tmp_path):
        records = [_record(subject=f"m{i}", date=f"2024-01-{i + 1:02d}") for i in range(5)]
        adapter = _adapter_with_records("alice@example.com", records, tmp_path=tmp_path)
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(mailbox_tasks, query="", limit=2)
        assert response.data["total"] == 2

    def test_accounts_subset_restricts_search(self, mailbox_tasks, tmp_path):
        mailbox_tasks.client_handler = FakeClientHandler(
            {"bob@example.com": FakeClient([_email()])}
        )
        adapter = _adapter_with_records(
            "alice@example.com", [_record()], tmp_path=tmp_path
        )
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(mailbox_tasks, accounts=["bob@example.com"])
        assert response.success
        assert response.data["accounts"] == ["bob@example.com"]
        assert all(
            r["account"] == "bob@example.com" for r in response.data["results"]
        )

    def test_broken_imap_account_is_skipped_not_fatal(self, mailbox_tasks):
        mailbox_tasks.client_handler = FakeClientHandler(
            {
                "dead@example.com": FakeClient([_email()], boom=True),
                "live@example.com": FakeClient([_email(subject="Alive")]),
            }
        )

        response = self._run(mailbox_tasks, query="")
        assert response.success
        accounts = response.data["accounts"]
        assert "live@example.com" in accounts
        assert "dead@example.com" not in accounts

    def test_structured_criteria_dict_is_accepted(
        self, mailbox_tasks, tmp_path
    ):
        adapter = _adapter_with_records(
            "alice@example.com",
            [
                _record(subject="Quarterly report", date="2024-01-02"),
                _record(subject="Lunch plans", date="2024-01-01"),
            ],
            tmp_path=tmp_path,
        )
        mailbox_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(
            mailbox_tasks, criteria={"subject": "quarterly"}
        )
        assert response.success
        assert [r["subject"] for r in response.data["results"]] == ["Quarterly report"]

    def test_unknown_account_returns_empty_not_error(self, mailbox_tasks):
        response = self._run(mailbox_tasks, accounts=["ghost@example.com"])
        assert response.success
        assert response.data["results"] == []
        assert response.data["accounts"] == []


# ── GET /nostr/directory ─────────────────────────────────────────────────


class TestNostrDirectory:
    @pytest.fixture()
    def nostr_tasks(self, tmp_path, monkeypatch):
        import src.routers.nostr_tasks as module

        monkeypatch.setattr(module, "nostr_handler", FakeNostrHandler())
        return module

    def _run(self, module, **kwargs):
        return asyncio.run(module.nostr_directory(**kwargs))

    def test_own_identity_is_listed_as_self(self, nostr_tasks, tmp_path):
        identity = generate_nostr_identity()
        adapter = _adapter_with_records(
            "alice@example.com", [], tmp_path=tmp_path, identity=identity
        )
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks)
        assert response.success
        contacts = response.data["contacts"]
        own = next(c for c in contacts if c["npub"] == identity.public_key_bech32)
        assert own["self"] is True
        assert own["account"] == "alice@example.com"
        assert own["address"] is None

    def test_recipients_and_senders_are_collected(self, nostr_tasks, tmp_path):
        adapter = _adapter_with_records(
            "alice@example.com",
            [
                _record(
                    sender="Bob <bob@example.com>",
                    to=["carol@example.com"],
                    cc=["dave@example.com"],
                    date="2024-01-02T00:00:00Z",
                ),
                _record(
                    sender="Bob <bob@example.com>",
                    to=["carol@example.com"],
                    date="2024-01-01T00:00:00Z",
                ),
            ],
            tmp_path=tmp_path,
        )
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks)
        contacts = {c["address"]: c for c in response.data["contacts"]}
        assert contacts["bob@example.com"]["name"] == "Bob"
        assert contacts["bob@example.com"]["messages"] == 2
        assert contacts["carol@example.com"]["messages"] == 2
        assert contacts["dave@example.com"]["messages"] == 1
        assert contacts["bob@example.com"]["last_seen"] == "2024-01-02T00:00:00Z"

    def test_npub_contacts_are_normalized(self, nostr_tasks, tmp_path):
        identity = generate_nostr_identity()
        adapter = _adapter_with_records(
            "alice@example.com",
            [_record(sender=identity.public_key_bech32, date="2024-01-01T00:00:00Z")],
            tmp_path=tmp_path,
        )
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks)
        entry = next(
            c for c in response.data["contacts"] if c["npub"] == identity.public_key_bech32
        )
        assert entry["address"] is None
        assert entry["messages"] == 1

    def test_query_filters_contacts(self, nostr_tasks, tmp_path):
        adapter = _adapter_with_records(
            "alice@example.com",
            [
                _record(sender="Bob <bob@example.com>"),
                _record(sender="Carol <carol@example.com>"),
            ],
            tmp_path=tmp_path,
        )
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks, q="bob")
        addresses = [c["address"] for c in response.data["contacts"]]
        assert addresses == ["bob@example.com"]

    def test_query_matches_own_account_address(self, nostr_tasks, tmp_path):
        identity = generate_nostr_identity()
        adapter = _adapter_with_records(
            "alice@example.com", [], tmp_path=tmp_path, identity=identity
        )
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks, q="alice@")
        accounts = [c["account"] for c in response.data["contacts"]]
        assert accounts == ["alice@example.com"]

    def test_limit_caps_contacts(self, nostr_tasks, tmp_path):
        records = [_record(sender=f"p{i} <p{i}@example.com>") for i in range(10)]
        adapter = _adapter_with_records("alice@example.com", records, tmp_path=tmp_path)
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks, limit=3)
        assert len(response.data["contacts"]) == 3

    def test_broken_mailbox_does_not_fail_request(self, nostr_tasks, tmp_path):
        adapter = _adapter_with_records("alice@example.com", [], tmp_path=tmp_path)

        def _boom(*, limit=5000):
            raise OSError("mailbox unreadable")

        adapter.fetch_records = _boom  # type: ignore[method-assign]
        nostr_tasks.nostr_handler = FakeNostrHandler({"alice@example.com": adapter})

        response = self._run(nostr_tasks)
        assert response.success

    def test_empty_directory_is_successful(self, nostr_tasks):
        response = self._run(nostr_tasks)
        assert response.success
        assert response.data["contacts"] == []
