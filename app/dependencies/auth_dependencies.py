from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db_session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.security import decode_access_token

settings = get_settings()


def get_current_user_optional(request: Request, db: Session = Depends(get_db_session)) -> User | None:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        return None
    subject = payload.get("sub")
    if not subject:
        return None
    return UserRepository(db).get_by_email(subject)


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user
