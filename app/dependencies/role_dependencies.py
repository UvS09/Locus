from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.dependencies.auth_dependencies import get_current_user
from app.models.user import User
from app.utils.enums import UserRole


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        return user

    return dependency
