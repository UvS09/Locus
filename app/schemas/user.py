from pydantic import BaseModel, EmailStr, Field

from app.utils.enums import UserRole


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    role: UserRole
    custom_role_id: int | None = None
    team_id: int | None = None
    designation_id: int | None = None
    department_id: int | None = None
    division_id: int | None = None
    reports_to_user_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    role: UserRole
    custom_role_id: int | None = None
    team_id: int | None = None
    designation_id: int | None = None
    department_id: int | None = None
    division_id: int | None = None
    reports_to_user_id: int | None = None
    is_active: bool = True
