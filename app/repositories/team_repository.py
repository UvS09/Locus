from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.team import Team


class TeamRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Team]:
        return self.db.scalars(select(Team).order_by(Team.name)).all()

    def get_by_id(self, team_id: int) -> Team | None:
        return self.db.get(Team, team_id)

    def get_by_name(self, name: str) -> Team | None:
        return self.db.scalar(select(Team).where(Team.name == name))

    def get_by_manager_id(self, manager_id: int) -> Team | None:
        return self.db.scalar(select(Team).where(Team.manager_id == manager_id))

    def create(self, team: Team) -> Team:
        self.db.add(team)
        self.db.flush()
        return team
