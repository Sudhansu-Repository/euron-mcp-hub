"""Tickets: a help desk behind a bearer token, in two versions.

1.4.0 (at /mcp) adds `add_comment` and a stricter `update_status`; 1.3.2 (at /v1/mcp) is
the release before it. Both serve the same queue. Pointing a catalog entry from one URL
to the other is a real upgrade as far as discovery can tell.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

LATEST = "1.4.0"
PREVIOUS = "1.3.2"
Status = Literal["open", "pending", "resolved", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]
_NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)


@dataclass
class Ticket:
    id: str
    title: str
    description: str
    priority: str
    status: str
    requester: str
    assignee: str | None = None
    comments: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


SEED: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "VPN drops every 30 minutes",
        "Remote staff in Lisbon lose the VPN tunnel twice an hour.",
        "high",
        "open",
        "ines.costa@lumenlabs.example",
        "Daniel Okafor",
    ),
    (
        "Invoice PDF shows the wrong VAT number",
        "October invoices for EU customers print the old VAT id.",
        "urgent",
        "open",
        "billing@acmefreight.example",
        "Priya Sharma",
    ),
    (
        "Request: access to the analytics workspace",
        "New analyst needs read access to dashboards.",
        "normal",
        "pending",
        "sam.rivera@lumenlabs.example",
        None,
    ),
    (
        "Laptop battery swelling",
        "Battery bulging on a 2023 laptop, replacement needed.",
        "high",
        "open",
        "tomas.berg@lumenlabs.example",
        "Daniel Okafor",
    ),
    (
        "SSO login loop on Safari",
        "Users bounce between the IdP and the app after the update.",
        "urgent",
        "pending",
        "it@northwindtraders.example",
        "Mei Lin",
    ),
    (
        "Printer on floor 3 jams",
        "Tray 2 jams on every duplex job.",
        "low",
        "resolved",
        "front.desk@lumenlabs.example",
        "Daniel Okafor",
    ),
    (
        "Export to CSV times out",
        "Exports above 50k rows fail after 60 seconds.",
        "normal",
        "open",
        "ops@acmefreight.example",
        "Priya Sharma",
    ),
    (
        "Password reset email not arriving",
        "Reset emails land in spam for one customer domain.",
        "normal",
        "resolved",
        "support@globalbank.example",
        "Mei Lin",
    ),
    (
        "Add SAML for the Contractors group",
        "Contractors need SSO through the partner IdP.",
        "normal",
        "open",
        "security@lumenlabs.example",
        None,
    ),
    (
        "Dashboard numbers differ from the report",
        "Weekly revenue on the dashboard is 2% above the PDF.",
        "high",
        "open",
        "finance@lumenlabs.example",
        "Priya Sharma",
    ),
    (
        "Mobile app crashes on launch (Android 15)",
        "Crash on startup after the 6.2 release.",
        "urgent",
        "open",
        "qa@lumenlabs.example",
        "Mei Lin",
    ),
    (
        "Close the old staging account",
        "Decommission staging-2 and archive its logs.",
        "low",
        "closed",
        "platform@lumenlabs.example",
        "Daniel Okafor",
    ),
)


class Queue:
    def __init__(self) -> None:
        self._ids = itertools.count(1201)
        self.tickets: dict[str, Ticket] = {}
        for index, (title, description, priority, status, requester, assignee) in enumerate(SEED):
            created = (_NOW - timedelta(days=12 - index, hours=index * 2)).isoformat()
            ticket_id = f"TCK-{next(self._ids)}"
            self.tickets[ticket_id] = Ticket(
                ticket_id,
                title,
                description,
                priority,
                status,
                requester,
                assignee,
                created_at=created,
                updated_at=created,
            )

    def new_id(self) -> str:
        return f"TCK-{next(self._ids)}"

    def find(self, ticket_id: str) -> Ticket:
        ticket = self.tickets.get(ticket_id.strip().upper())
        if ticket is None:
            raise ToolError(f"Ticket {ticket_id} does not exist.")
        return ticket


def _summary(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "priority": ticket.priority,
        "status": ticket.status,
        "assignee": ticket.assignee,
    }


def build_tickets_server(queue: Queue, *, version: str = LATEST) -> MCPServer:
    latest = version == LATEST
    server = MCPServer(
        "tickets",
        title="Help desk",
        description="Customer and internal support tickets.",
        version=version,
        log_level="WARNING",
        instructions="Look a ticket up before changing it; never close one you did not resolve.",
    )
    read_only = ToolAnnotations(read_only_hint=True)

    @server.tool(
        description="List tickets, newest first, filtered by status or priority.",
        annotations=read_only,
    )
    def list_tickets(
        status: Status | None = None,
        priority: Priority | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> list[dict[str, Any]]:
        chosen = [
            t
            for t in queue.tickets.values()
            if (status is None or t.status == status)
            and (priority is None or t.priority == priority)
        ]
        chosen.sort(key=lambda t: t.created_at, reverse=True)
        return [_summary(t) for t in chosen[:limit]]

    @server.tool(description="Read one ticket with its comments.", annotations=read_only)
    def get_ticket(ticket_id: str) -> dict[str, Any]:
        return asdict(queue.find(ticket_id))

    @server.tool(description="Open a new ticket.")
    def create_ticket(
        title: Annotated[str, Field(min_length=3, max_length=200)],
        description: Annotated[str, Field(max_length=5000)] = "",
        priority: Priority = "normal",
        requester_email: str = "agent@lumenlabs.example",
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        ticket = Ticket(
            queue.new_id(),
            title,
            description,
            priority,
            "open",
            requester_email,
            created_at=now,
            updated_at=now,
        )
        queue.tickets[ticket.id] = ticket
        return _summary(ticket)

    status_help = (
        "Move a ticket to another status. Resolving or closing needs a note explaining why."
        if latest
        else "Change the status of a ticket."
    )

    @server.tool(description=status_help)
    def update_status(ticket_id: str, status: Status, note: str | None = None) -> dict[str, Any]:
        ticket = queue.find(ticket_id)
        if latest and status in {"resolved", "closed"} and not (note and note.strip()):
            raise ToolError("Add a note explaining the resolution before resolving or closing.")
        ticket.status = status
        ticket.updated_at = datetime.now(UTC).isoformat()
        if note:
            ticket.comments.append({"body": note, "internal": True, "at": ticket.updated_at})
        return _summary(ticket)

    @server.tool(description="Assign a ticket to a person.")
    def assign_ticket(
        ticket_id: str, assignee: Annotated[str, Field(min_length=2, max_length=120)]
    ) -> dict[str, Any]:
        ticket = queue.find(ticket_id)
        ticket.assignee = assignee
        ticket.updated_at = datetime.now(UTC).isoformat()
        return _summary(ticket)

    if latest:

        @server.tool(
            description="Add a comment to a ticket, visible to the requester unless internal."
        )
        def add_comment(
            ticket_id: str,
            body: Annotated[str, Field(min_length=1, max_length=5000)],
            internal: bool = False,
        ) -> dict[str, Any]:
            ticket = queue.find(ticket_id)
            ticket.comments.append(
                {"body": body, "internal": internal, "at": datetime.now(UTC).isoformat()}
            )
            return {"id": ticket.id, "comments": len(ticket.comments)}

    @server.tool(
        description="Delete a ticket and its history.",
        annotations=ToolAnnotations(destructive_hint=True),
    )
    def delete_ticket(ticket_id: str) -> str:
        ticket = queue.find(ticket_id)
        del queue.tickets[ticket.id]
        return f"Deleted {ticket.id}."

    @server.resource("tickets://queue/summary", description="Open tickets by priority.")
    def queue_summary() -> str:
        counts: dict[str, int] = {}
        for ticket in queue.tickets.values():
            if ticket.status in {"open", "pending"}:
                counts[ticket.priority] = counts.get(ticket.priority, 0) + 1
        return "\n".join(f"{p}: {counts.get(p, 0)}" for p in ("urgent", "high", "normal", "low"))

    @server.prompt(description="Triage a ticket: priority, owner and a first reply.")
    def triage_ticket(ticket_id: str) -> str:
        return (
            f"Read ticket {ticket_id} with get_ticket. Suggest a priority and an assignee, and "
            "draft a short first reply to the requester."
        )

    return server
