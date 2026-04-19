from fastapi import APIRouter, Depends, HTTPException

from backend.models.schemas import ChatHistoryResponse, ChatRequest, ChatResponse
from backend.services.auth_store import AuthenticatedUser, get_current_user
from backend.services.chat_service import get_chat_history_for_session, run_chat_turn

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return await run_chat_turn(
            current_user=current_user,
            session_id=body.session_id,
            message=body.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
def get_chat_history(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return get_chat_history_for_session(current_user=current_user, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
