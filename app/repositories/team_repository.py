from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.department import Department
from app.models.team import Team


class TeamRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Team]:
        stmt = (
            select(Team)
            .options(
                selectinload(Team.department).selectinload(Department.division),
                selectinload(Team.manager),
                selectinload(Team.members),
            )
            .order_by(Team.name)
        )
        return self.db.scalars(stmt).all()

    def get_by_id(self, team_id: int) -> Team | None:
        stmt = (
            select(Team)
            .options(
                selectinload(Team.department).selectinload(Department.division),
                selectinload(Team.manager),
                selectinload(Team.members),
            )
            .where(Team.id == team_id)
        )
        return self.db.scalar(stmt)

    def get_by_name(self, name: str) -> Team | None:
        return self.db.scalar(select(Team).where(Team.name == name))

    def get_by_manager_id(self, manager_id: int) -> Team | None:
        return self.db.scalar(select(Team).where(Team.manager_id == manager_id))

    def create(self, team: Team) -> Team:
        self.db.add(team)
        self.db.flush()
        return team
