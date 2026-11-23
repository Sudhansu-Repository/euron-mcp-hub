"""Notes: a team notebook. Read and write tools, a resource template and two prompts."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

VERSION = "2.1.0"
_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@dataclass
class Note:
    id: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    author: str = "team"
    updated_at: str = ""


SEED: tuple[tuple[str, str, list[str], str], ...] = (
    (
        "Q4 launch checklist",
        "Freeze the pricing page by Nov 3. Legal review of the new terms is due Nov 5. "
        "Support macros for the launch go live on Nov 10, the press briefing is on Nov 12.",
        ["launch", "planning"],
        "Priya Sharma",
    ),
    (
        "On-call handoff, week 43",
        "Two pages this week, both from the payments queue backing up after 02:00 UTC. "
        "Runbook step 4 (drain the retry queue) fixed both. Watch the nightly export job.",
        ["ops", "on-call"],
        "Daniel Okafor",
    ),
    (
        "Customer interview: Acme Freight",
        "They track 1,200 shipments a day and want alerts when a carrier misses a scan. "
        "Biggest pain: reconciling invoices against delivered weight. Would pay for an API.",
        ["research", "customers"],
        "Mei Lin",
    ),
    (
        "Postmortem: payments latency spike",
        "On Oct 14 p95 checkout latency reached 4.1 s for 23 minutes. Cause: a missing index "
        "on refunds.created_at after the partition change. Action items: index, alert on p95.",
        ["incident", "ops"],
        "Daniel Okafor",
    ),
    (
        "Pricing experiment results",
        "The annual plan banner raised annual conversions from 18% to 26% with no change in "
        "churn after 30 days. Recommendation: ship it to every region in November.",
        ["research", "pricing"],
        "Priya Sharma",
    ),
    (
        "Team offsite agenda",
        "Day one: roadmap review and customer panel. Day two: architecture deep dive on the "
        "event pipeline, then planning for the first half of next year.",
        ["team"],
        "Mei Lin",
    ),
    (
        "API v1 deprecation timeline",
        "Announce on Nov 1, warning headers from Dec 1, read-only from Feb 1, removal on "
        "Apr 1. Twelve customers still call v1 weekly; account managers own the outreach.",
        ["engineering", "planning"],
        "Priya Sharma",
    ),
    (
        "Security review: SSO rollout",
        "SAML for enterprise accounts, OIDC for everyone else. Enforce SSO per domain, keep "
        "one break-glass admin per workspace, and log every assertion failure.",
        ["security"],
        "Daniel Okafor",
    ),
)


def build_notes_server() -> MCPServer:
    counter = itertools.count(1)
    notes: dict[str, Note] = {}
    for index, (title, body, tags, author) in enumerate(SEED):
        note_id = f"n-{next(counter):03d}"
        updated = (_NOW - timedelta(days=len(SEED) - index, hours=index)).isoformat()
        notes[note_id] = Note(note_id, title, body, tags, author, updated)

    server = MCPServer(
        "notes",
        title="Team notes",
        description="A shared notebook for plans, postmortems and research.",
        version=VERSION,
        log_level="WARNING",
        instructions="Search before creating a note; titles are short and specific.",
    )

    def find(note_id: str) -> Note:
        note = notes.get(note_id)
        if note is None:
            raise ToolError(f"Note {note_id} does not exist.")
        return note

    @server.tool(
        description="Search notes by words in the title or body.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def search_notes(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> list[dict[str, Any]]:
        words = [word for word in query.lower().split() if word]
        scored = []
        for note in notes.values():
            text = f"{note.title} {note.body} {' '.join(note.tags)}".lower()
            score = sum(text.count(word) for word in words)
            if score:
                scored.append((score, note))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [
            {"id": n.id, "title": n.title, "tags": n.tags, "updated_at": n.updated_at}
            for _, n in scored[:limit]
        ]

    @server.tool(
        description="List notes, newest first, optionally only those with a tag.",
        annotations=ToolAnnotations(read_only_hint=True),
    )
    def list_notes(
        tag: str | None = None, limit: Annotated[int, Field(ge=1, le=100)] = 20
    ) -> list[dict[str, Any]]:
        chosen = [n for n in notes.values() if tag is None or tag in n.tags]
        chosen.sort(key=lambda n: n.updated_at, reverse=True)
        return [{"id": n.id, "title": n.title, "tags": n.tags} for n in chosen[:limit]]

    @server.tool(
        description="Read one note in full.", annotations=ToolAnnotations(read_only_hint=True)
    )
    def get_note(note_id: str) -> dict[str, Any]:
        return asdict(find(note_id))

    @server.tool(description="Create a note.")
    def create_note(
        title: Annotated[str, Field(min_length=1, max_length=120)],
        body: Annotated[str, Field(max_length=10_000)],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        note_id = f"n-{next(counter):03d}"
        note = Note(note_id, title, body, tags or [], "mcp client", datetime.now(UTC).isoformat())
        notes[note_id] = note
        return asdict(note)

    @server.tool(description="Replace the title or the body of a note.")
    def update_note(
        note_id: str, title: str | None = None, body: str | None = None
    ) -> dict[str, Any]:
        note = find(note_id)
        if title is not None:
            note.title = title
        if body is not None:
            note.body = body
        note.updated_at = datetime.now(UTC).isoformat()
        return asdict(note)

    @server.tool(
        description="Delete a note permanently.",
        annotations=ToolAnnotations(destructive_hint=True),
    )
    def delete_note(note_id: str) -> str:
        find(note_id)
        del notes[note_id]
        return f"Deleted {note_id}."

    @server.resource("notes://recent", description="The five most recently updated notes.")
    def recent() -> str:
        latest = sorted(notes.values(), key=lambda n: n.updated_at, reverse=True)[:5]
        return "\n".join(f"{n.id}  {n.title}" for n in latest)

    @server.resource("notes://note/{note_id}", description="One note as plain text.")
    def note_text(note_id: str) -> str:
        note = notes.get(note_id)
        if note is None:
            raise ResourceNotFoundError(f"Note {note_id} does not exist.")
        return f"# {note.title}\n\n{note.body}"

    @server.prompt(description="Summarise every note with a tag into decisions and open questions.")
    def summarize_notes(tag: str) -> str:
        return (
            f"Read every note tagged '{tag}' with search_notes and get_note. Summarise them as "
            "decisions made, open questions and owners, in at most ten bullet points."
        )

    @server.prompt(description="Draft a weekly review from this week's notes.")
    def weekly_review() -> str:
        return "List this week's notes, then write a short weekly review: wins, risks, next steps."

    return server
