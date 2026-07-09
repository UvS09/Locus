# Product Requirements Document

## Product Name

Locus

## Document Purpose

This PRD describes the current product requirements and implemented functional scope of Locus. It focuses on business goals, users, permissions, workflows, data behavior, reporting, integrations, and operational expectations. It intentionally excludes UI and visual design details.

## Product Summary

Locus is an internal enterprise work management system for organizing and tracking delivery work across an organizational hierarchy. It supports:

- Organization administration
- Role-based access and custom roles
- Multi-level operational hierarchy
- Project and work-item lifecycle management
- Progress rollups across the hierarchy
- Notifications and auditability
- Manager and employee analytics
- Exportable reports

The product is intended for internal enterprise usage where work needs to be created, assigned, tracked, reviewed, escalated, and reported through management layers.

## Business Objective

Locus exists to give the organization a structured system for:

- Managing users, reporting relationships, teams, departments, and divisions
- Tracking work from project level down to task and sub-task level
- Providing visibility according to organizational authority
- Measuring delivery progress, workload, completion, blocked work, and overdue work
- Creating a reliable historical trail of operational changes

## Target Users

### 1. Administrator

Administrators manage the system and organization configuration.

Primary responsibilities:

- Manage users
- Manage custom roles
- Manage divisions, departments, and teams
- Assign managers and members to teams
- Review audit logs
- Review organization-wide reports
- Access workspace-level organization data
- Impersonate users in non-production environments

### 2. Operating Head

Operating Heads have the broadest operational visibility within the manager role family.

Primary responsibilities:

- View cross-division delivery state
- Review division-wise workload and progress
- Review organization-wide blocked and overdue work in visible scope
- Review member hierarchy across divisions and departments
- Monitor recent updates and upcoming deadlines

### 3. Division Head

Division Heads manage and monitor work inside their division.

Primary responsibilities:

- View department-wise delivery state within the division
- Review department workload, progress, blocked work, and overdue work
- Monitor members within the division
- Review employee analytics in allowed scope

### 4. Department Head

Department Heads manage work inside their department.

Primary responsibilities:

- View team-level or department-level work performance
- Review completion, workload, blocked work, and overdue work
- Monitor department members
- Review scoped employee analytics

### 5. Team Member / Employee

Employees execute and update work within their permitted scope.

Primary responsibilities:

- Track assigned work
- Track created work
- Update task and work-item status
- Create allowed child work under accessible parent items
- Add comments and manage sub-tasks on accessible tasks
- Review personal analytics and department updates in visible scope

## Product Scope

The current product scope includes the following functional areas:

- Authentication and session management
- Role-based and scope-based authorization
- User, role, team, department, and division administration
- Reporting hierarchy management
- Hierarchical work management
- Task and sub-task execution
- Progress rollup and status propagation
- Notifications
- Audit logging
- Reporting and analytics
- Report export
- Deployment configuration for local, server, Docker, and Vercel-compatible runtime use

## Organizational Model

Locus models organizational visibility through:

- Division
- Department
- Team
- Reporting manager
- Access level
- Designation scope

### Supported Scope Levels

- `SYSTEM_ADMINISTRATOR`
- `OPERATING_HEAD`
- `DIVISION_HEAD`
- `DEPARTMENT_HEAD`
- `TEAM_MEMBER`

### Reporting and Visibility Rules

- Admins can view and manage the entire organization.
- Operating Heads can view the full visible operating structure.
- Division Heads can view users and work inside their division.
- Department Heads can view users and work inside their department.
- Team Members can view work in their own team or department when allowed by business logic, plus work directly assigned to or created by them.

## Access Model

### Base Access Levels

The system uses three route authorization levels:

- `ADMIN`
- `MANAGER`
- `EMPLOYEE`

### Custom Roles

Admins can create custom roles. A custom role includes:

- Role name
- Mapped base access level
- Description

Custom roles provide business-specific naming while preserving route-level security based on the mapped base access level.

## Work Management Model

### Hierarchy

The active work hierarchy is:

```text
Project
  -> Milestone
    -> Activity
      -> Task
        -> Sub-task
```

Internal compatibility naming:

- `OBJECTIVE` = Project
- `WORKSTREAM` = Milestone

### Parent-Child Rules

- Projects have no parent.
- Milestones must belong to a project.
- Activities must belong to a milestone.
- Tasks must belong to an activity.
- Sub-tasks must belong to a task.

### Work Item Fields and Behaviors

At a functional level, work items support:

- Title
- Description
- Level
- Parent
- Team ownership
- Creator
- Assignee
- Priority
- Due date
- Status
- Progress percentage
- Completion timestamp
- Comments
- Children

### Ownership Rules

- The creator becomes the owner/creator automatically.
- Employees can only create work at allowed levels.
- Admins cannot create delivery work items.

### Create Permissions

- Managers can create all delivery levels in their scope.
- Employees can create milestones, activities, tasks, and sub-tasks where they have access.
- Employees cannot create projects.

### Edit Permissions

- Admins can edit any accessible work item.
- Managers can edit work items in their visible scope.
- Employees can edit accessible work items only when they are the creator or assignee.

### Delete Permissions

- A user may delete a work item tree only if they are allowed to delete the root and all descendants in that tree.
- Deletion is prevented when descendant ownership or permission rules are violated.

## Status and Progress Model

### Supported Statuses

The current work-item status model includes:

- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `COMPLETED`
- `CLOSED`

### Leaf Item Progress Rules

- `PENDING` sets progress to `0%`
- `IN_PROGRESS` keeps partial progress and defaults to `50%` when needed
- `BLOCKED` preserves last earned progress
- `COMPLETED` sets progress to `100%`
- `CLOSED` sets progress to `100%`

### Rollup Rules

Progress is recalculated recursively from child items upward.

- Parent progress is based on the average progress of direct children.
- If all children are completed or closed, the parent becomes completed.
- If a parent was manually blocked, blocked state is preserved.
- If children have progress, blocked state, or in-progress state, the parent becomes in progress.
- Parent completion can never exceed the logical state of children.

### Blocking Rules

- Blocking changes work state, not achieved progress.
- Blocked work remains visible as blocked and retains earned progress.
- Reopened or resumed work does not remain incorrectly at `100%`.

## Comments and Sub-Tasks

The system supports task execution collaboration through:

- Comments on tasks
- Sub-task creation
- Sub-task completion toggling

### Sub-task Rules

- Sub-tasks belong to a task
- Sub-task status updates affect parent execution visibility
- Due-date-sensitive toggling behavior is enforced in business logic

## Notifications

The system includes user notifications for operational events.

Current behavior includes:

- Notification generation for participant-relevant work updates
- Notification visibility in user scope
- Mark single notification as read
- Mark all notifications as read

Recipients generally include relevant creator and assignee participants, excluding the acting user.

## Audit Logging

The system maintains audit logs for important administrative and business actions.

Audit log capabilities include:

- Storing actor, action, entity type, entity id, timestamp, and details
- Listing recent audit history
- Filtering audit logs
- Exporting audit logs

Audit logs are intended to support accountability, traceability, and administrative review.

## User and Organization Administration

### User Management

Administrators can:

- Create users
- Update users
- Activate or deactivate users
- Delete users
- Assign roles or custom roles
- Assign designations
- Assign divisions, departments, and teams
- Assign reporting managers
- Set initial or temporary access conditions

### Organization Structure Management

Administrators can:

- Create divisions
- Delete divisions
- Create departments
- Delete departments
- Create teams
- Delete teams
- Assign team managers
- Assign team members

### Manager Relationship Model

Users can be assigned a reporting manager and manager chain metadata to represent internal reporting structure.

## Authentication and Security Requirements

### Authentication

The system uses:

- Login with email and password
- JWT access token generation
- HTTP-only cookie session storage
- Logout support

### Account Bootstrap

- If no users exist, the signup flow can create the first admin.
- After bootstrap, user management is handled through administration flows.

### Profile and Password Management

Users can:

- View and update profile data
- Change password
- Be forced to change password where configured

### Security Constraints

- Cookies support secure and same-site configuration
- Sensitive actions rely on backend authorization, not template-only restrictions
- Secret key and runtime settings are environment-driven

## Dashboard and Analytics Requirements

This section describes information and business visibility, not presentation.

### Admin Analytics

Admins can review:

- Total users
- Active users
- Teams
- Active objectives/projects
- Active tasks
- Overdue tasks
- Custom role distribution
- Team workload summary
- Portfolio progress
- Objective, milestone, activity, and task completion
- Recent notifications
- Recent audit activity

### Operating Head Analytics

Operating Heads can review:

- Active members
- Active projects
- Open work items
- Completed work today
- Division-wise workload
- Division-wise completion
- Division-wise roadmap metrics
- Division-wise blocked and overdue counts
- Cross-division member hierarchy
- Overall completion across hierarchy levels
- Upcoming deadlines
- Recent updates

### Division Head Analytics

Division Heads can review:

- Division-scoped members
- Department-wise completion
- Department-wise workload
- Active projects in visible scope
- Open work
- Blocked work
- Overdue work
- Recent updates
- Upcoming deadlines
- Employee analytics in visible scope

### Department Head Analytics

Department Heads can review:

- Department-scoped members
- Team-wise or department-scoped completion
- Team-wise or department-scoped workload
- Active projects in visible scope
- Open work
- Blocked work
- Overdue work
- Recent updates
- Upcoming deadlines
- Employee analytics in visible scope

### Employee Analytics

Employees can review:

- Assigned work
- Created work
- Pending count
- In-progress count
- Blocked count
- Completed count
- Average progress
- Personal completion rate
- Upcoming deadlines
- Recent updates on assigned work
- Department updates in visible scope
- Department open work

## Reporting Requirements

### Admin Reports

The product supports organization-level reporting covering:

- Objective completion
- Milestone completion
- Activity completion
- Task completion
- Portfolio progress
- Overdue work
- Employee productivity
- Manager productivity
- Team performance
- Trends in completed work

### Manager Reports

Managers can review employee analytics within their allowed scope, including:

- Assigned work
- Open work
- In-progress work
- Blocked work
- Overdue work
- Completed work
- Completion rate
- Average progress

### Employee Analytics

Employees have access to personal analytics and scoped work signals relevant to their own execution.

## Export Requirements

The product supports exports for:

- Admin reports
- Manager reports
- Audit logs

Supported export formats currently include:

- `XLSX`
- `PDF`
- `CSV` where applicable through export helpers

## Search, Filtering, and Workspace Review

The product includes operational filtering capabilities for:

- Work items by query, status, and team
- Users by query, role, team, and active state
- Audit logs by actor, action, entity, and date

Admin workspace review supports:

- Organization-wide work inspection
- Project listing
- Task listing
- Status-based grouping

## Notifications and Operational Updates

The product supports operational awareness through:

- Recent updates in user-visible scope
- Department updates
- Notifications
- Upcoming deadlines
- Blocked work review
- Overdue work review

## Non-Functional Requirements

### Deployment

The system must support:

- Local development with SQLite
- Production deployment with PostgreSQL
- Uvicorn-based server deployment
- Docker/Docker Compose deployment
- Vercel-compatible Python deployment using the same FastAPI app entry

### Configuration

The system must be configurable through environment variables, including:

- App environment
- Debug mode
- Secret key
- Cookie settings
- Database connection settings
- Database startup initialization behavior

### Data Initialization

The system currently supports startup-driven schema initialization and seed behavior for simple deployments.

### Test Coverage

The system must remain verifiable through automated tests for:

- Authentication
- Role protection
- Authorization
- Progress behavior
- Blocking behavior
- Reporting exports
- Route rendering

## Current Constraints and Assumptions

- The product is intended for internal enterprise usage.
- Persistent local SQLite should be treated as development-only.
- Production persistence should use PostgreSQL.
- Authorization is governed by both route-level role checks and scope-aware service rules.
- The product currently uses server-rendered flows and backend-driven business logic.

## Out of Scope for This PRD

This document does not define:

- UI layout
- Visual design
- Styling
- Frontend component behavior

## Source of Truth

This PRD is based on the current implemented application behavior in:

- `README.md`
- `SYSTEM_DESIGN.md`
- `app/routes/`
- `app/services/`
- `app/models/`
- `tests/`
