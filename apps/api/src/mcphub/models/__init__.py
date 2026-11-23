"""Every model, imported here so `Base.metadata` is complete for Alembic and the tests."""

from mcphub.models.audit import AuditEvent
from mcphub.models.client import Client, ClientKey, PolicyRule
from mcphub.models.server import (
    HealthCheck,
    Prompt,
    Resource,
    Server,
    ServerSecret,
    ServerVersion,
    Tool,
)
from mcphub.models.tool_call import ToolCall
from mcphub.models.user import User

__all__ = [
    "AuditEvent",
    "Client",
    "ClientKey",
    "HealthCheck",
    "PolicyRule",
    "Prompt",
    "Resource",
    "Server",
    "ServerSecret",
    "ServerVersion",
    "Tool",
    "ToolCall",
    "User",
]
