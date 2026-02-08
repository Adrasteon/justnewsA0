"""
Base Model - Advanced Implementation
Abstract base class for database models with ORM-like functionality

Features:
- ORM-like Interface: Object-relational mapping for database tables
- Validation: Pydantic-based model validation
- Relationships: Support for foreign key relationships
- Query Building: Fluent query API
- Migration Support: Automatic schema generation
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel as PydanticBaseModel, Field, ConfigDict, field_serializer
from pydantic_core import PydanticUndefined

from common.observability import get_logger

from ..core.connection_pool import DatabaseConnectionPool

logger = get_logger(__name__)

T = TypeVar('T', bound='BaseModel')


class BaseModel(PydanticBaseModel, ABC):
    """
    Abstract base class for database models with ORM-like functionality
    """

    # Database table name (must be set by subclasses)
    __tablename__: str = ""

    # Primary key field
    id: Optional[int] = Field(default=None, description="Primary key")

    # Timestamps
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))

    # Database connection pool (set at class level)
    _connection_pool: Optional[DatabaseConnectionPool] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime fields to ISO format"""
        return value.isoformat() if value else None

    @classmethod
    def set_connection_pool(cls, pool: DatabaseConnectionPool):
        """Set the database connection pool for all models"""
        cls._connection_pool = pool

    @classmethod
    def get_connection_pool(cls) -> DatabaseConnectionPool:
        """Get the database connection pool"""
        if cls._connection_pool is None:
            raise RuntimeError("Database connection pool not set. Call set_connection_pool() first.")
        return cls._connection_pool

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate CREATE TABLE SQL for this model

        Returns:
            SQL CREATE TABLE statement
        """
        if not cls.__tablename__:
            raise ValueError("Model must define __tablename__")

        fields = []

        # Get field definitions from Pydantic
        for field_name, field_info in cls.model_fields.items():
            sql_type = cls._get_sql_type(field_info)
            constraints = cls._get_field_constraints(field_name, field_info)

            field_def = f"{field_name} {sql_type}"
            if constraints:
                field_def += f" {constraints}"

            fields.append(field_def)

        # Add primary key constraint if id field exists
        if 'id' in cls.model_fields:
            fields.append("PRIMARY KEY (id)")

        # Add unique constraints
        unique_constraints = cls._get_unique_constraints()
        fields.extend(unique_constraints)

        # Add foreign key constraints
        fk_constraints = cls._get_foreign_key_constraints()
        fields.extend(fk_constraints)

        fields_sql = ",\n    ".join(fields)

        return f"""
CREATE TABLE IF NOT EXISTS {cls.__tablename__} (
    {fields_sql}
);
"""

    @classmethod
    def _get_sql_type(cls, field_info) -> str:
        """Convert Pydantic field type to SQL type"""
        # Get the annotation from field_info
        field_type = field_info.annotation

        # Handle Optional types
        if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
            # Get the non-None type from Optional
            non_none_types = [t for t in field_type.__args__ if t is not type(None)]
            if non_none_types:
                field_type = non_none_types[0]

        type_mapping = {
            int: "INTEGER",
            str: "VARCHAR(255)",
            float: "DECIMAL(10,2)",
            bool: "BOOLEAN",
            datetime: "TIMESTAMP WITH TIME ZONE",
            dict: "JSONB",
            list: "JSONB"
        }

        return type_mapping.get(field_type, "VARCHAR(255)")

    @classmethod
    def _get_field_constraints(cls, field_name: str, field_info) -> str:
        """Get SQL constraints for a field"""
        constraints = []

        # NOT NULL constraint
        if field_info.is_required() and field_name != 'id':  # id can be auto-generated
            constraints.append("NOT NULL")

        # DEFAULT constraint
        if field_info.default is not PydanticUndefined and field_name not in ['created_at', 'updated_at']:
            default_val = field_info.default
            if isinstance(default_val, str):
                constraints.append(f"DEFAULT '{default_val}'")
            elif isinstance(default_val, bool):
                constraints.append(f"DEFAULT {str(default_val).upper()}")
            else:
                constraints.append(f"DEFAULT {default_val}")

        # AUTO_INCREMENT for id field
        if field_name == 'id':
            constraints.append("GENERATED ALWAYS AS IDENTITY")

        return " ".join(constraints)

    @classmethod
    def _get_unique_constraints(cls) -> List[str]:
        """Get unique constraints (to be implemented by subclasses)"""
        return []

    @classmethod
    def _get_foreign_key_constraints(cls) -> List[str]:
        """Get foreign key constraints (to be implemented by subclasses)"""
        return []

    @classmethod
    def _get_field_types(cls) -> Dict[str, str]:
        """Get field types mapping for the model"""
        field_types = {}
        for field_name, field_info in cls.model_fields.items():
            sql_type = cls._get_sql_type(field_info)
            field_types[field_name] = sql_type
        return field_types

    @classmethod
    def _get_primary_key_field(cls) -> Optional[str]:
        """Get the primary key field name"""
        for field_name, field_info in cls.model_fields.items():
            # Check if field has primary_key in json_schema_extra (Pydantic v2 style)
            if hasattr(field_info, 'json_schema_extra') and field_info.json_schema_extra:
                if field_info.json_schema_extra.get('primary_key'):
                    return field_name
            # Check if field name is 'id' (default primary key)
            if field_name == 'id':
                return field_name
        return None

    @classmethod
    def create(cls, **kwargs) -> T:
        """
        Create a new model instance and save to database

        Returns:
            Created model instance
        """
        instance = cls(**kwargs)
        instance.save()
        return instance

    @classmethod
    def get(cls: Type[T], id: int) -> Optional[T]:
        """
        Get model instance by ID

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        pool = cls.get_connection_pool()
        query = f"SELECT * FROM {cls.__tablename__} WHERE id = %s"
        results = pool.execute_query(query, (id,))

        if results:
            return cls(**results[0])
        return None

    @classmethod
    def filter(cls: Type[T], **kwargs) -> List[T]:
        """
        Filter model instances by field values

        Returns:
            List of matching model instances
        """
        pool = cls.get_connection_pool()

        # Build WHERE clause
        where_parts = []
        values = []
        for field, value in kwargs.items():
            where_parts.append(f"{field} = %s")
            values.append(value)

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"

        query = f"SELECT * FROM {cls.__tablename__} WHERE {where_clause}"
        results = pool.execute_query(query, tuple(values))

        return [cls(**row) for row in results]

    @classmethod
    def all(cls: Type[T]) -> List[T]:
        """
        Get all model instances

        Returns:
            List of all model instances
        """
        pool = cls.get_connection_pool()
        query = f"SELECT * FROM {cls.__tablename__}"
        results = pool.execute_query(query)

        return [cls(**row) for row in results]

    def save(self) -> T:
        """
        Save model instance to database

        Returns:
            Updated model instance
        """
        pool = self.get_connection_pool()

        # Prepare data
        data = self.model_dump(exclude_unset=True, exclude={'id'})
        data['updated_at'] = datetime.now(UTC)

        if self.id is None:
            # INSERT
            data['created_at'] = datetime.now(UTC)
            fields = list(data.keys())
            values = list(data.values())
            placeholders = ['%s'] * len(fields)

            query = f"""
            INSERT INTO {self.__tablename__}
            ({', '.join(fields)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
            """

            results = pool.execute_query(query, tuple(values))
            if results:
                self.id = results[0]['id']
        else:
            # UPDATE
            fields = [k for k in data.keys() if k != 'created_at']
            values = [data[k] for k in fields]
            set_clause = ', '.join([f"{field} = %s" for field in fields])

            query = f"""
            UPDATE {self.__tablename__}
            SET {set_clause}
            WHERE id = %s
            """

            values.append(self.id)
            pool.execute_query(query, tuple(values), fetch=False)

        return self

    def delete(self):
        """Delete model instance from database"""
        if self.id is None:
            raise ValueError("Cannot delete model without ID")

        pool = self.get_connection_pool()
        query = f"DELETE FROM {self.__tablename__} WHERE id = %s"
        pool.execute_query(query, (self.id,), fetch=False)

    def refresh(self) -> T:
        """
        Refresh model instance from database

        Returns:
            Updated model instance
        """
        if self.id is None:
            raise ValueError("Cannot refresh model without ID")

        pool = self.get_connection_pool()
        query = f"SELECT * FROM {self.__tablename__} WHERE id = %s"
        results = pool.execute_query(query, (self.id,))

        if results:
            # Update instance with fresh data
            for key, value in results[0].items():
                setattr(self, key, value)

        return self

    @classmethod
    def count(cls) -> int:
        """
        Count total number of records

        Returns:
            Number of records in table
        """
        pool = cls.get_connection_pool()
        query = f"SELECT COUNT(*) as count FROM {cls.__tablename__}"
        results = pool.execute_query(query)

        return results[0]['count'] if results else 0

    @classmethod
    def exists(cls, id: int) -> bool:
        """
        Check if record exists by ID

        Args:
            id: Primary key value

        Returns:
            True if record exists
        """
        pool = cls.get_connection_pool()
        query = f"SELECT 1 FROM {cls.__tablename__} WHERE id = %s LIMIT 1"
        results = pool.execute_query(query, (id,))

        return len(results) > 0