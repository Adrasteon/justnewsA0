"""
JustNews Authorization Service

Handles role-based access control (RBAC), permission validation, and user role management.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiofiles
from pydantic import BaseModel, Field

from ..models import AuthorizationError, SecurityConfig

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """Permission levels"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


class Role(BaseModel):
    """Role definition"""

    name: str
    description: str
    permissions: list[str] = Field(default_factory=list)
    inherits_from: list[str] = Field(default_factory=list)  # Parent roles


class Permission(BaseModel):
    """Permission definition"""

    name: str
    description: str
    resource: str  # Resource pattern (e.g., "articles:*", "users:123")
    actions: list[str] = Field(default_factory=list)  # read, write, delete, admin


@dataclass
class RoleHierarchy:
    """Role hierarchy for inheritance"""

    roles: dict[str, Role]
    permissions: dict[str, Permission]

    def get_all_permissions(self, role_name: str) -> set[str]:
        """Get all permissions for a role including inherited ones"""
        permissions = set()
        visited = set()

        def collect_permissions(role: str):
            if role in visited:
                return
            visited.add(role)

            if role in self.roles:
                role_obj = self.roles[role]
                permissions.update(role_obj.permissions)

                # Collect from parent roles
                for parent in role_obj.inherits_from:
                    collect_permissions(parent)

        collect_permissions(role_name)
        return permissions

    def has_permission(self, role_name: str, permission: str) -> bool:
        """Check if role has specific permission"""
        all_permissions = self.get_all_permissions(role_name)
        return permission in all_permissions


class AuthorizationService:
    """
    Authorization service for role-based access control

    Manages user roles, permissions, and access control decisions.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._role_hierarchy = RoleHierarchy(
            roles=self._get_default_roles(), permissions=self._get_default_permissions()
        )
        self._user_roles: dict[int, list[str]] = {}  # user_id -> roles
        self._resource_permissions: dict[
            str, dict[str, list[str]]
        ] = {}  # resource -> action -> roles

    def _get_default_roles(self) -> dict[str, Role]:
        """Get default role definitions"""
        return {
            "user": Role(
                name="user",
                description="Basic user with read access",
                permissions=[
                    "articles:read",
                    "comments:read",
                    "profile:read",
                    "profile:write",
                ],
            ),
            "moderator": Role(
                name="moderator",
                description="Content moderator",
                permissions=[
                    "articles:read",
                    "articles:write",
                    "comments:read",
                    "comments:write",
                    "comments:delete",
                    "users:read",
                    "reports:read",
                ],
                inherits_from=["user"],
            ),
            "admin": Role(
                name="admin",
                description="System administrator",
                permissions=["users:*", "system:*", "audit:*"],
                inherits_from=["moderator"],
            ),
            "analyst": Role(
                name="analyst",
                description="Data analyst",
                permissions=["analytics:read", "reports:read", "data:export"],
                inherits_from=["user"],
            ),
        }

    def _get_default_permissions(self) -> dict[str, Permission]:
        """Get default permission definitions"""
        return {
            "articles:read": Permission(
                name="articles:read",
                description="Read articles",
                resource="articles",
                actions=["read"],
            ),
            "articles:write": Permission(
                name="articles:write",
                description="Create and edit articles",
                resource="articles",
                actions=["write"],
            ),
            "articles:delete": Permission(
                name="articles:delete",
                description="Delete articles",
                resource="articles",
                actions=["delete"],
            ),
            "comments:read": Permission(
                name="comments:read",
                description="Read comments",
                resource="comments",
                actions=["read"],
            ),
            "comments:write": Permission(
                name="comments:write",
                description="Create comments",
                resource="comments",
                actions=["write"],
            ),
            "comments:delete": Permission(
                name="comments:delete",
                description="Delete comments",
                resource="comments",
                actions=["delete"],
            ),
            "users:read": Permission(
                name="users:read",
                description="Read user information",
                resource="users",
                actions=["read"],
            ),
            "users:write": Permission(
                name="users:write",
                description="Modify user information",
                resource="users",
                actions=["write"],
            ),
            "users:delete": Permission(
                name="users:delete",
                description="Delete users",
                resource="users",
                actions=["delete"],
            ),
            "system:*": Permission(
                name="system:*",
                description="Full system access",
                resource="system",
                actions=["*"],
            ),
            "audit:*": Permission(
                name="audit:*",
                description="Audit log access",
                resource="audit",
                actions=["*"],
            ),
        }

    async def initialize(self) -> None:
        """Initialize authorization service"""
        await self._load_role_data()
        logger.info("AuthorizationService initialized")

    async def shutdown(self) -> None:
        """Shutdown authorization service"""
        await self._save_role_data()
        logger.info("AuthorizationService shutdown")

    async def check_permission(
        self, user_id: int, permission: str, resource: str | None = None
    ) -> bool:
        """
        Check if user has specific permission

        Args:
            user_id: User ID
            permission: Permission to check (e.g., "articles:read")
            resource: Optional specific resource identifier

        Returns:
            True if user has permission
        """
        try:
            # Get user roles
            user_roles = self._user_roles.get(user_id, [])

            # Check each role
            for role in user_roles:
                if self._role_hierarchy.has_permission(role, permission):
                    # Additional resource-level check if needed
                    if resource and not self._check_resource_permission(
                        role, permission, resource
                    ):
                        continue
                    return True

            return False

        except Exception as e:
            logger.error(f"Permission check failed for user {user_id}: {e}")
            return False

    async def get_user_permissions(self, user_id: int) -> list[str]:
        """
        Get all permissions for a user

        Args:
            user_id: User ID

        Returns:
            List of permission strings
        """
        user_roles = self._user_roles.get(user_id, [])
        all_permissions = set()

        for role in user_roles:
            all_permissions.update(self._role_hierarchy.get_all_permissions(role))

        return list(all_permissions)

    async def get_user_roles(self, user_id: int) -> list[str]:
        """
        Get roles assigned to user

        Args:
            user_id: User ID

        Returns:
            List of role names
        """
        return self._user_roles.get(user_id, [])

    async def assign_role(self, user_id: int, role: str) -> None:
        """
        Assign role to user

        Args:
            user_id: User ID
            role: Role name to assign

        Raises:
            AuthorizationError: If role doesn't exist
        """
        if role not in self._role_hierarchy.roles:
            raise AuthorizationError(f"Role '{role}' does not exist")

        if user_id not in self._user_roles:
            self._user_roles[user_id] = []

        if role not in self._user_roles[user_id]:
            self._user_roles[user_id].append(role)
            await self._save_role_data()
            logger.info(f"Assigned role '{role}' to user {user_id}")

    async def revoke_role(self, user_id: int, role: str) -> None:
        """
        Revoke role from user

        Args:
            user_id: User ID
            role: Role name to revoke
        """
        if user_id in self._user_roles and role in self._user_roles[user_id]:
            self._user_roles[user_id].remove(role)
            await self._save_role_data()
            logger.info(f"Revoked role '{role}' from user {user_id}")

    async def create_role(self, role: Role) -> None:
        """
        Create new role

        Args:
            role: Role definition

        Raises:
            AuthorizationError: If role already exists
        """
        if role.name in self._role_hierarchy.roles:
            raise AuthorizationError(f"Role '{role.name}' already exists")

        self._role_hierarchy.roles[role.name] = role
        await self._save_role_data()
        logger.info(f"Created role '{role.name}'")

    async def update_role(self, role_name: str, updates: dict[str, Any]) -> None:
        """
        Update existing role

        Args:
            role_name: Name of role to update
            updates: Fields to update

        Raises:
            AuthorizationError: If role doesn't exist
        """
        if role_name not in self._role_hierarchy.roles:
            raise AuthorizationError(f"Role '{role_name}' does not exist")

        role = self._role_hierarchy.roles[role_name]

        for key, value in updates.items():
            if hasattr(role, key):
                setattr(role, key, value)

        await self._save_role_data()
        logger.info(f"Updated role '{role_name}'")

    async def delete_role(self, role_name: str) -> None:
        """
        Delete role

        Args:
            role_name: Role name to delete

        Raises:
            AuthorizationError: If role is in use or doesn't exist
        """
        if role_name not in self._role_hierarchy.roles:
            raise AuthorizationError(f"Role '{role_name}' does not exist")

        # Check if role is assigned to any users
        for user_roles in self._user_roles.values():
            if role_name in user_roles:
                raise AuthorizationError(
                    f"Cannot delete role '{role_name}' - it is assigned to users"
                )

        del self._role_hierarchy.roles[role_name]
        await self._save_role_data()
        logger.info(f"Deleted role '{role_name}'")

    async def create_permission(self, permission: Permission) -> None:
        """
        Create new permission

        Args:
            permission: Permission definition

        Raises:
            AuthorizationError: If permission already exists
        """
        if permission.name in self._role_hierarchy.permissions:
            raise AuthorizationError(f"Permission '{permission.name}' already exists")

        self._role_hierarchy.permissions[permission.name] = permission
        await self._save_role_data()
        logger.info(f"Created permission '{permission.name}'")

    async def add_permission_to_role(self, role_name: str, permission: str) -> None:
        """
        Add permission to role

        Args:
            role_name: Role name
            permission: Permission name

        Raises:
            AuthorizationError: If role or permission doesn't exist
        """
        if role_name not in self._role_hierarchy.roles:
            raise AuthorizationError(f"Role '{role_name}' does not exist")

        if permission not in self._role_hierarchy.permissions:
            raise AuthorizationError(f"Permission '{permission}' does not exist")

        role = self._role_hierarchy.roles[role_name]
        if permission not in role.permissions:
            role.permissions.append(permission)
            await self._save_role_data()
            logger.info(f"Added permission '{permission}' to role '{role_name}'")

    async def remove_permission_from_role(
        self, role_name: str, permission: str
    ) -> None:
        """
        Remove permission from role

        Args:
            role_name: Role name
            permission: Permission name
        """
        if role_name in self._role_hierarchy.roles:
            role = self._role_hierarchy.roles[role_name]
            if permission in role.permissions:
                role.permissions.remove(permission)
                await self._save_role_data()
                logger.info(
                    f"Removed permission '{permission}' from role '{role_name}'"
                )

    async def get_all_roles(self) -> dict[str, dict[str, Any]]:
        """
        Get all roles with their details

        Returns:
            Dict of role name -> role data
        """
        return {
            name: {
                "name": role.name,
                "description": role.description,
                "permissions": role.permissions,
                "inherits_from": role.inherits_from,
            }
            for name, role in self._role_hierarchy.roles.items()
        }

    async def get_all_permissions(self) -> dict[str, dict[str, Any]]:
        """
        Get all permissions with their details

        Returns:
            Dict of permission name -> permission data
        """
        return {
            name: {
                "name": perm.name,
                "description": perm.description,
                "resource": perm.resource,
                "actions": perm.actions,
            }
            for name, perm in self._role_hierarchy.permissions.items()
        }

    async def get_role_users(self, role_name: str) -> list[int]:
        """
        Get all users with a specific role

        Args:
            role_name: Role name

        Returns:
            List of user IDs
        """
        user_ids = []
        for user_id, roles in self._user_roles.items():
            if role_name in roles:
                user_ids.append(user_id)
        return user_ids

    def _check_resource_permission(
        self, role: str, permission: str, resource: str
    ) -> bool:
        """
        Check resource-level permission

        Args:
            role: Role name
            permission: Permission string
            resource: Resource identifier

        Returns:
            True if role has permission for resource
        """
        # Parse permission (e.g., "articles:read" -> resource="articles", action="read")
        if ":" in permission:
            resource_type, action = permission.split(":", 1)
        else:
            return False

        # Check resource permissions
        resource_perms = self._resource_permissions.get(resource, {})
        allowed_roles = resource_perms.get(action, [])

        return role in allowed_roles

    async def set_resource_permission(
        self, resource: str, action: str, roles: list[str]
    ) -> None:
        """
        Set resource-level permission

        Args:
            resource: Resource identifier
            action: Action (read, write, delete)
            roles: List of roles that can perform this action
        """
        if resource not in self._resource_permissions:
            self._resource_permissions[resource] = {}

        self._resource_permissions[resource][action] = roles
        await self._save_role_data()

    async def get_status(self) -> dict[str, Any]:
        """
        Get authorization service status

        Returns:
            Status information
        """
        return {
            "status": "healthy",
            "total_roles": len(self._role_hierarchy.roles),
            "total_permissions": len(self._role_hierarchy.permissions),
            "users_with_roles": len(self._user_roles),
            "resource_permissions": len(self._resource_permissions),
        }

    async def _load_role_data(self) -> None:
        """Load role and permission data from storage"""
        try:
            async with aiofiles.open("data/authorization.json") as f:
                data = json.loads(await f.read())

                # Load roles
                roles_data = data.get("roles", {})
                for name, role_dict in roles_data.items():
                    self._role_hierarchy.roles[name] = Role(**role_dict)

                # Load permissions
                perms_data = data.get("permissions", {})
                for name, perm_dict in perms_data.items():
                    self._role_hierarchy.permissions[name] = Permission(**perm_dict)

                # Load user roles
                self._user_roles = data.get("user_roles", {})

                # Load resource permissions
                self._resource_permissions = data.get("resource_permissions", {})

                logger.info(
                    f"Loaded authorization data: {len(self._role_hierarchy.roles)} roles, "
                    f"{len(self._user_roles)} users with roles"
                )

        except FileNotFoundError:
            logger.info("No authorization data file found, using defaults")
        except Exception as e:
            logger.error(f"Failed to load authorization data: {e}")

    async def _save_role_data(self) -> None:
        """Save role and permission data to storage"""
        try:
            data = {
                "roles": {
                    name: {
                        "name": role.name,
                        "description": role.description,
                        "permissions": role.permissions,
                        "inherits_from": role.inherits_from,
                    }
                    for name, role in self._role_hierarchy.roles.items()
                },
                "permissions": {
                    name: {
                        "name": perm.name,
                        "description": perm.description,
                        "resource": perm.resource,
                        "actions": perm.actions,
                    }
                    for name, perm in self._role_hierarchy.permissions.items()
                },
                "user_roles": self._user_roles,
                "resource_permissions": self._resource_permissions,
            }

            async with aiofiles.open("data/authorization.json", "w") as f:
                await f.write(json.dumps(data, indent=2))

        except Exception as e:
            logger.error(f"Failed to save authorization data: {e}")
