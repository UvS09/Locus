from app.config import get_settings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.comment import Comment
from app.models.department import Department
from app.models.designation import Designation
from app.models.division import Division
from app.models.notification import Notification
from app.models.role import Role
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.models.work_item import WorkItem
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import AuditService
from app.utils.enums import DesignationScope, UserRole
from app.utils.password_generator import generate_temporary_password
from app.utils.security import hash_password, validate_password_strength

settings = get_settings()


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_service = AuditService(db)

    def list_users(self) -> list[User]:
        return self.user_repo.list_all()

    def list_custom_roles(self) -> list[Role]:
        return self.db.scalars(select(Role).order_by(Role.name)).all()

    def list_designations(self) -> list[Designation]:
        return self.db.scalars(select(Designation).order_by(Designation.rank.desc(), Designation.name)).all()

    def list_divisions(self) -> list[Division]:
        return self.db.scalars(select(Division).order_by(Division.name)).all()

    def list_departments(self, division_id: int | None = None) -> list[Department]:
        stmt = select(Department).order_by(Department.name)
        if division_id is not None:
            stmt = stmt.where(Department.division_id == division_id)
        return self.db.scalars(stmt).all()

    def create_role(self, actor: User, *, name: str, access_level: UserRole, description: str | None = None) -> Role:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create roles.")
        cleaned_name = name.strip()
        if len(cleaned_name) < 2:
            raise ValueError("Role name must be at least 2 characters.")
        existing = self.db.scalar(select(Role).where(func.lower(Role.name) == cleaned_name.lower()))
        if existing:
            raise ValueError("A role with this name already exists.")

        role = Role(name=cleaned_name, access_level=access_level, description=description.strip() if description else None)
        self.db.add(role)
        self.db.flush()
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="role_created",
            entity_type="Role",
            entity_id=role.id,
            details={"name": role.name, "access_level": role.access_level},
        )
        return role

    def has_any_users(self) -> bool:
        return self.user_repo.count() > 0

    def list_managers(self) -> list[User]:
        return self.user_repo.list_by_role(UserRole.MANAGER)

    def list_employees(self) -> list[User]:
        return self.user_repo.list_by_role(UserRole.EMPLOYEE)

    def list_team_members(self, team_id: int) -> list[User]:
        return self.user_repo.list_team_members(team_id)

    def get_user(self, user_id: int) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")
        return user

    def list_visible_users(self, actor: User) -> list[User]:
        users = self.user_repo.list_all()
        return [user for user in users if self.can_view_user(actor, user)]

    def can_view_user(self, actor: User, target: User) -> bool:
        if actor.role == UserRole.ADMIN:
            return True
        if actor.scope_level in {DesignationScope.SYSTEM_ADMINISTRATOR, DesignationScope.OPERATING_HEAD}:
            return True
        if actor.scope_level == DesignationScope.DIVISION_HEAD:
            return bool(actor.division_id and target.division_id == actor.division_id)
        if actor.scope_level == DesignationScope.DEPARTMENT_HEAD:
            return bool(actor.department_id and target.department_id == actor.department_id)
        return bool(
            (actor.team_id and target.team_id == actor.team_id)
            or (actor.department_id and target.department_id == actor.department_id)
        )

    def scope_label(self, actor: User) -> str:
        if actor.role == UserRole.ADMIN:
            return "Organization"
        if actor.scope_level == DesignationScope.OPERATING_HEAD:
            return "All divisions"
        if actor.scope_level == DesignationScope.DIVISION_HEAD and actor.division:
            return actor.division.name
        if actor.scope_level == DesignationScope.DEPARTMENT_HEAD and actor.department:
            return actor.department.name
        if actor.team:
            return actor.team.name
        return actor.display_designation

    def create_division(self, actor: User, *, name: str, description: str | None = None) -> Division:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create divisions.")
        cleaned_name = name.strip()
        if len(cleaned_name) < 2:
            raise ValueError("Division name must be at least 2 characters.")
        existing = self.db.scalar(select(Division).where(func.lower(Division.name) == cleaned_name.lower()))
        if existing:
            raise ValueError("A division with this name already exists.")
        division = Division(name=cleaned_name, description=description.strip() if description else None)
        self.db.add(division)
        self.db.flush()
        return division

    def delete_division(self, actor: User, division_id: int) -> Division:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can delete divisions.")
        division = self.db.get(Division, division_id)
        if not division:
            raise ValueError("Division not found.")
        for user in self.db.query(User).filter(User.division_id == division.id).all():
            user.division_id = None
            if user.department and user.department.division_id == division.id:
                user.department_id = None
            if user.team and user.team.department and user.team.department.division_id == division.id:
                user.team_id = None
        for department in list(division.departments):
            self.delete_department(actor, department.id)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="division_deleted",
            entity_type="Division",
            entity_id=division.id,
            details={"name": division.name},
        )
        self.db.delete(division)
        self.db.flush()
        return division

    def create_department(self, actor: User, *, name: str, division_id: int, description: str | None = None) -> Department:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create departments.")
        division = self.db.get(Division, division_id)
        if not division:
            raise ValueError("Division not found.")
        cleaned_name = name.strip()
        if len(cleaned_name) < 2:
            raise ValueError("Department name must be at least 2 characters.")
        department = Department(
            name=cleaned_name,
            division_id=division.id,
            description=description.strip() if description else None,
        )
        self.db.add(department)
        self.db.flush()
        return department

    def delete_department(self, actor: User, department_id: int) -> Department:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can delete departments.")
        department = self.db.get(Department, department_id)
        if not department:
            raise ValueError("Department not found.")
        from app.services.team_service import TeamService

        team_service = TeamService(self.db)
        for user in self.db.query(User).filter(User.department_id == department.id).all():
            user.department_id = None
            user.team_id = None
        for team in list(department.teams):
            team_service.delete_team(actor, team.id)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="department_deleted",
            entity_type="Department",
            entity_id=department.id,
            details={"name": department.name},
        )
        self.db.delete(department)
        self.db.flush()
        return department

    def _resolve_org_context(
        self,
        *,
        team_id: int | None,
        department_id: int | None,
        division_id: int | None,
    ) -> tuple[Team | None, Department | None, Division | None]:
        team = self.db.get(Team, team_id) if team_id else None
        department = self.db.get(Department, department_id) if department_id else None
        division = self.db.get(Division, division_id) if division_id else None

        if team and team.department_id:
            department = self.db.get(Department, team.department_id)
        if department and department.division_id:
            division = self.db.get(Division, department.division_id)

        if team_id and not team:
            raise ValueError("Selected team not found.")
        if department_id and not department:
            raise ValueError("Selected department not found.")
        if division_id and not division:
            raise ValueError("Selected division not found.")
        return team, department, division

    def _resolve_reporting_manager(self, reports_to_user_id: int | None) -> User | None:
        if reports_to_user_id is None:
            return None
        manager = self.get_user(reports_to_user_id)
        if not manager.is_active:
            raise ValueError("Reporting manager must be active.")
        return manager

    def _resolve_designation(self, designation_id: int | None, role: UserRole) -> Designation | None:
        if designation_id is not None:
            designation = self.db.get(Designation, designation_id)
            if not designation:
                raise ValueError("Designation not found.")
            return designation
        default_map = {
            UserRole.ADMIN: "System Administrator",
            UserRole.MANAGER: "Department Head",
            UserRole.EMPLOYEE: "Team Member",
        }
        return self.db.scalar(select(Designation).where(Designation.name == default_map[role]))

    def _validate_hierarchy_assignment(
        self,
        *,
        designation: Designation | None,
        team: Team | None,
        department: Department | None,
        division: Division | None,
        reporting_manager: User | None,
    ) -> tuple[Team | None, Department | None, Division | None, User | None]:
        if designation is None:
            return team, department, division, reporting_manager

        scope = designation.scope_level

        if scope in {DesignationScope.SYSTEM_ADMINISTRATOR, DesignationScope.OPERATING_HEAD}:
            return None, None, None, None

        if scope == DesignationScope.DIVISION_HEAD:
            if division is None:
                raise ValueError("Division Head must be assigned to a division.")
            return None, None, division, None

        if scope in {DesignationScope.DEPARTMENT_HEAD, DesignationScope.TEAM_MEMBER}:
            if department is None:
                raise ValueError(f"{designation.name.replace(' (CIO)', '')} must be assigned to a department.")
            return None, department, division or department.division, None

        return team, department, division, reporting_manager

    def create_user(self, actor: User, payload: UserCreate) -> tuple[User, str]:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create users.")
        if self.user_repo.get_by_email(payload.email):
            raise ValueError("A user with this email already exists.")

        custom_role = self._get_custom_role(payload.custom_role_id)
        access_role = custom_role.access_level if custom_role else payload.role
        team, department, division = self._resolve_org_context(
            team_id=payload.team_id,
            department_id=payload.department_id,
            division_id=payload.division_id,
        )
        reporting_manager = self._resolve_reporting_manager(payload.reports_to_user_id)
        designation = self._resolve_designation(payload.designation_id, access_role)
        team, department, division, reporting_manager = self._validate_hierarchy_assignment(
            designation=designation,
            team=team,
            department=department,
            division=division,
            reporting_manager=reporting_manager,
        )
        temporary_password = generate_temporary_password()
        user = User(
            full_name=payload.full_name,
            email=payload.email.lower(),
            role=access_role,
            custom_role_id=custom_role.id if custom_role else None,
            designation_id=designation.id if designation else None,
            division_id=division.id if division else None,
            department_id=department.id if department else None,
            reports_to_user_id=reporting_manager.id if reporting_manager else None,
            manager_chain=str(reporting_manager.id) if reporting_manager else None,
            team_id=team.id if team else None,
            password_hash=hash_password(temporary_password),
            must_change_password=True,
            is_active=True,
            is_protected=False,
        )
        self.user_repo.create(user)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_created",
            entity_type="User",
            entity_id=user.id,
            details={
                "role": user.display_role,
                "access_level": user.role,
                "designation": user.display_designation,
                "team_id": user.team_id,
                "department_id": user.department_id,
                "division_id": user.division_id,
            },
        )
        return user, temporary_password

    def update_user(self, actor: User, user_id: int, payload: UserUpdate) -> User:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can update users.")
        user = self.get_user(user_id)
        normalized_email = payload.email.lower()
        existing_user = self.user_repo.get_by_email(normalized_email)
        if existing_user and existing_user.id != user.id:
            raise ValueError("A user with this email already exists.")
        custom_role = self._get_custom_role(payload.custom_role_id)
        access_role = custom_role.access_level if custom_role else payload.role
        team, department, division = self._resolve_org_context(
            team_id=payload.team_id,
            department_id=payload.department_id,
            division_id=payload.division_id,
        )
        designation = self._resolve_designation(payload.designation_id, access_role)
        reporting_manager = self._resolve_reporting_manager(payload.reports_to_user_id)
        team, department, division, reporting_manager = self._validate_hierarchy_assignment(
            designation=designation,
            team=team,
            department=department,
            division=division,
            reporting_manager=reporting_manager,
        )
        user.full_name = payload.full_name
        user.email = normalized_email
        user.role = access_role
        user.custom_role_id = custom_role.id if custom_role else None
        user.designation_id = designation.id if designation else None
        user.team_id = team.id if team else None
        user.department_id = department.id if department else None
        user.division_id = division.id if division else None
        user.reports_to_user_id = reporting_manager.id if reporting_manager else None
        user.manager_chain = str(reporting_manager.id) if reporting_manager else None
        user.is_active = payload.is_active
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_updated",
            entity_type="User",
            entity_id=user.id,
            details={
                "email": user.email,
                "role": user.display_role,
                "designation": user.display_designation,
                "access_level": user.role,
                "team_id": user.team_id,
                "department_id": user.department_id,
                "division_id": user.division_id,
                "is_active": user.is_active,
            },
        )
        return user

    def deactivate_user(self, actor: User, user_id: int) -> User:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can deactivate users.")
        user = self.get_user(user_id)
        user.is_active = False
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_deactivated",
            entity_type="User",
            entity_id=user.id,
        )
        return user

    def delete_user(self, actor: User, user_id: int) -> User:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can delete users.")

        user = self.get_user(user_id)

        for item in self.db.query(WorkItem).filter(WorkItem.assigned_to_id == user.id).all():
            item.assigned_to_id = None
        for item in self.db.query(WorkItem).filter(WorkItem.created_by_id == user.id).all():
            item.created_by_id = None
        for team in self.db.query(Team).filter(Team.manager_id == user.id).all():
            team.manager_id = None
        for log in self.db.query(AuditLog).filter(AuditLog.actor_user_id == user.id).all():
            log.actor_user_id = None
        for notification in self.db.query(Notification).filter(Notification.user_id == user.id).all():
            self.db.delete(notification)
        for comment in self.db.query(Comment).filter(Comment.author_id == user.id).all():
            self.db.delete(comment)
        for legacy_task in self.db.query(Task).filter((Task.assigned_to_id == user.id) | (Task.created_by_id == user.id)).all():
            self.db.delete(legacy_task)

        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_deleted",
            entity_type="User",
            entity_id=user.id,
            details={"email": user.email, "full_name": user.full_name},
        )
        self.user_repo.delete(user)
        return user

    def bootstrap_admin(self, *, full_name: str, email: str, password: str) -> User:
        if settings.is_production:
            raise ValueError("Signup is disabled in production.")
        if self.has_any_users():
            raise ValueError("Signup is available only for the first local admin.")
        if not email.lower().endswith(settings.allowed_email_suffix):
            raise ValueError(f"Email must end with {settings.allowed_email_suffix}.")
        validate_password_strength(password)

        user = User(
            full_name=full_name,
            email=email.lower(),
            role=UserRole.ADMIN,
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
        )
        self.user_repo.create(user)
        self.audit_service.log_action(
            actor_user_id=user.id,
            action="bootstrap_admin_created",
            entity_type="User",
            entity_id=user.id,
        )
        return user

    def _get_custom_role(self, role_id: int | None) -> Role | None:
        if role_id is None:
            return None
        role = self.db.get(Role, role_id)
        if not role:
            raise ValueError("Custom role not found.")
        return role
