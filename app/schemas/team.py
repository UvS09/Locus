from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    manager_id: int | None = None


class TeamMemberAssignment(BaseModel):
    user_ids: list[int]
