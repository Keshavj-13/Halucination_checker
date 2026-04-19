import logging
import secrets
from typing import Optional

from backend.models.schemas import ChatHistoryResponse, ChatMessage, ChatResponse
from backend.services.auth_store import AuthenticatedUser, auth_store
from backend.services.llm_client import llm

logger = logging.getLogger("audit-api.chat")

CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant for the SAMSA chatbot platform. "
    "Use the recent conversation for context when it is relevant, and answer clearly."
)
CHAT_FALLBACK_REPLY = (
    "I saved your message, but I couldn't reach the chat model right now. "
    "Please check the LLM configuration or connection and try again."
)


def _format_chat_history(history: list[ChatMessage]) -> str:
    if not history:
        return "No previous conversation."

    return "\n".join(f"{item.role.title()}: {item.message}" for item in history)


def get_chat_history_for_session(
    *,
    current_user: AuthenticatedUser,
    session_id: str,
    limit: int = 50,
) -> ChatHistoryResponse:
    normalized_session_id = session_id.strip()
    messages = auth_store.get_chat_history(current_user.id, normalized_session_id, limit=limit)
    return ChatHistoryResponse(session_id=normalized_session_id, messages=messages)


async def run_chat_turn(
    *,
    current_user: AuthenticatedUser,
    message: str,
    session_id: Optional[str] = None,
) -> ChatResponse:
    normalized_message = message.strip()
    if not normalized_message:
        raise ValueError("Message cannot be empty.")

    active_session_id = session_id.strip() if session_id and session_id.strip() else secrets.token_urlsafe(16)
    prior_messages = auth_store.get_chat_history(current_user.id, active_session_id, limit=50)

    auth_store.save_chat_message(
        user_id=current_user.id,
        session_id=active_session_id,
        role="user",
        message=normalized_message,
    )

    prompt = (
        "Conversation so far:\n"
        f"{_format_chat_history(prior_messages)}\n\n"
        f"User: {normalized_message}"
    )

    try:
        reply = await llm.chat(prompt, system_prompt=CHAT_SYSTEM_PROMPT)
    except Exception as exc:
        logger.warning(
            "Chat model unavailable for user %s; returning fallback reply instead. Error: %s",
            current_user.id,
            exc,
        )
        reply = CHAT_FALLBACK_REPLY

    assistant_message = auth_store.save_chat_message(
        user_id=current_user.id,
        session_id=active_session_id,
        role="assistant",
        message=reply,
    )

    messages = auth_store.get_chat_history(current_user.id, active_session_id, limit=50)
    return ChatResponse(session_id=active_session_id, reply=assistant_message.message, messages=messages)
