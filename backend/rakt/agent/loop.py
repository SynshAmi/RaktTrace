"""The agent loop entry points (BUILD §5.4). Phase 1 stubs: accepted and ignored."""

from rakt.models import Inbound


def handle_inbound(msg: Inbound) -> None:
    """Called by the bot and by POST /api/sim/reply."""


def link_chat(start_param: str, chat_id: str, display_name: str) -> str:
    return "RaktTrace: chat linking isn't available yet."
