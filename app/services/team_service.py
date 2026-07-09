from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.models.work_item import WorkItem
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.team import TeamCreate
from app.services.audit_service import AuditService
from app.utils.enums import UserRole


class TeamService:
    def __init__(self, db: Session):
        self.db = db
        self.team_repo = TeamRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_service = AuditService(db)

    def list_teams(self) -> list[Team]:
        return self.team_repo.list_all()

    def get_team(self, team_id: int) -> Team:
        team = self.team_repo.get_by_id(team_id)
        if not team:
            raise ValueError("Team not found.")
        return team

    def get_team_for_manager(self, manager: User) -> Team:
        team = self.team_repo.get_by_manager_id(manager.id)
        if not team:
            raise ValueError("Manager is not assigned to a team.")
        return team

    def create_team(self, actor: User, payload: TeamCreate) -> Team:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create teams.")
        if self.team_repo.get_by_name(payload.name):
            raise ValueError("A team with this name already exists.")
        if payload.department_id is None:
            raise ValueError("Teams must belong to a department.")
        department = self.db.get(Department, payload.department_id)
        if not department:
            raise ValueError("Selected department is invalid.")
        team = Team(name=payload.name, description=payload.description, manager_id=payload.manager_id, department_id=department.id)
        self.team_repo.create(team)
        if payload.manager_id:
            manager = self.user_repo.get_by_id(payload.manager_id)
            if not manager or manager.role != UserRole.MANAGER:
                raise ValueError("Selected manager is invalid.")
            manager.team_id = team.id
            manager.department_id = department.id
            manager.division_id = department.division_id
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="team_created",
            entity_type="Team",
            entity_id=team.id,
        )
        return team

    def assign_manager(self, actor: User, team_id: int, manager_id: int) -> Team:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can assign managers.")
        team = self.get_team(team_id)
        manager = self.user_repo.get_by_id(manager_id)
        if not manager or manager.role != UserRole.MANAGER:
            raise ValueError("Manager not found.")
        team.manager_id = manager.id
        manager.team_id = team.id
        manager.department_id = team.department_id
        manager.division_id = team.department.division_id if team.department else manager.division_id
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="team_manager_assigned",
            entity_type="Team",
            entity_id=team.id,
            details={"manager_id": manager.id},
        )
        return team

    def assign_members(self, actor: User, team_id: int, user_ids: list[int]) -> Team:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can assign team members.")
        team = self.get_team(team_id)
        members = [self.user_repo.get_by_id(user_id) for user_id in user_ids]
        valid_members = [user for user in members if user is not None]
        for user in valid_members:
            if user.role == UserRole.ADMIN:
                raise ValueError("Admins cannot be assigned to teams.")
            user.team_id = team.id
            user.department_id = team.department_id
            user.division_id = team.department.division_id if team.department else user.division_id
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="team_members_assigned",
            entity_type="Team",
            entity_id=team.id,
            details={"user_ids": user_ids},
        )
        return team

    def delete_team(self, actor: User, team_id: int) -> Team:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can delete teams.")
        team = self.get_team(team_id)

        for user in list(team.members):
            user.team_id = None
            if user.department_id == team.department_id:
                user.department_id = None
            if team.department and user.division_id == team.department.division_id:
                user.division_id = None

        if team.manager:
            team.manager.team_id = None
            if team.manager.department_id == team.department_id:
                team.manager.department_id = None
            if team.department and team.manager.division_id == team.department.division_id:
                team.manager.division_id = None

        for work_item in self.db.query(WorkItem).filter(WorkItem.team_id == team.id).all():
            self.db.delete(work_item)
        for task in self.db.query(Task).filter(Task.team_id == team.id).all():
            self.db.delete(task)

        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="team_deleted",
            entity_type="Team",
            entity_id=team.id,
            details={"name": team.name},
        )
        self.db.delete(team)
        self.db.flush()
        return team
