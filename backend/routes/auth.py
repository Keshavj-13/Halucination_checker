import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from models.schemas import AuthResponse, CredentialsRequest, HistoryDetail, HistorySummary, UserProfile
from services.auth_store import AuthenticatedUser, auth_store, get_current_user

router = APIRouter(tags=["auth"])
logger = logging.getLogger("audit-api.auth")


@router.post("/auth/register", response_model=AuthResponse)
def register(body: CredentialsRequest):
    try:
        user = auth_store.create_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    token = auth_store.create_session(user.id)
    return AuthResponse(token=token, user=user.to_profile())


@router.post("/auth/login", response_model=AuthResponse)
def login(body: CredentialsRequest):
    user = auth_store.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = auth_store.create_session(user.id)
    return AuthResponse(token=token, user=user.to_profile())


@router.get("/auth/me", response_model=UserProfile)
def me(current_user: AuthenticatedUser = Depends(get_current_user)):
    return current_user.to_profile()


@router.post("/auth/logout")
def logout(
    current_user: AuthenticatedUser = Depends(get_current_user),
    authorization: Optional[str] = Header(default=None),
):
    token = (authorization or "").partition(" ")[2]
    if token:
        auth_store.delete_session(token)
    return {"status": "ok"}


@router.get("/history", response_model=List[HistorySummary])
def list_history(current_user: AuthenticatedUser = Depends(get_current_user)):
    return auth_store.list_history(current_user.id)


@router.get("/history/{history_id}", response_model=HistoryDetail)
def get_history(history_id: int, current_user: AuthenticatedUser = Depends(get_current_user)):
    detail = auth_store.get_history_detail(current_user.id, history_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="History item not found.")
    return detail
