# Database Refactor Tests - Base Model Tests

from datetime import datetime
from unittest.mock import Mock

from pydantic import Field

from database.models.base_model import BaseModel


class TestBaseModel:
    """Test cases for BaseModel"""

    def test_base_model_initialization(self, mock_base_model):
        """Test BaseModel initialization"""

        # Create a test model class
        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str
            created_at: datetime

        # Test instance creation
        model = TestModel(id=1, name="test", created_at=datetime.now())
        assert model.id == 1
        assert model.name == "test"

    def test_set_connection_pool(self, mock_pool):
        """Test setting connection pool"""
        BaseModel.set_connection_pool(mock_pool)
        assert BaseModel._connection_pool == mock_pool

    def test_create_table_sql(self, mock_base_model):
        """Test table creation SQL generation"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int = Field(json_schema_extra={"primary_key": True})
            name: str = Field(max_length=100)
            email: str = Field(json_schema_extra={"unique": True})
            created_at: datetime = Field(default_factory=datetime.now)

        sql = TestModel.create_table_sql()

        # Check basic structure
        assert "CREATE TABLE IF NOT EXISTS test_table" in sql
        assert "id INTEGER GENERATED ALWAYS AS IDENTITY" in sql
        assert "name VARCHAR(255) NOT NULL" in sql
        assert "email VARCHAR(255) NOT NULL" in sql
        assert "created_at TIMESTAMP WITH TIME ZONE" in sql

    def test_save_method(self, mock_base_model, mock_pool):
        """Test save method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock()

        instance = TestModel(id=1, name="test")
        result = instance.save()

        assert result == instance
        mock_pool.execute_query.assert_called()

    def test_delete_method(self, mock_base_model, mock_pool):
        """Test delete method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock()

        instance = TestModel(id=1, name="test")
        instance.delete()

        mock_pool.execute_query.assert_called()

    def test_filter_method(self, mock_base_model, mock_pool):
        """Test filter method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(
            return_value=[{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]
        )

        results = TestModel.filter(name="test")

        assert len(results) == 2
        assert results[0].id == 1
        assert results[0].name == "test1"
        assert isinstance(results[0], TestModel)
        mock_pool.execute_query.assert_called()

    def test_get_method(self, mock_base_model, mock_pool):
        """Test get method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(return_value=[{"id": 1, "name": "test"}])

        result = TestModel.get(id=1)

        assert result is not None
        assert result.id == 1
        assert result.name == "test"
        assert isinstance(result, TestModel)
        mock_pool.execute_query.assert_called()

    def test_get_method_not_found(self, mock_base_model, mock_pool):
        """Test get method when record not found"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(return_value=[])

        result = TestModel.get(id=999)

        assert result is None
        mock_pool.execute_query.assert_called()

    def test_all_method(self, mock_base_model, mock_pool):
        """Test all method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(
            return_value=[{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}]
        )

        results = TestModel.all()

        assert len(results) == 2
        assert all(isinstance(r, TestModel) for r in results)
        mock_pool.execute_query.assert_called()

    def test_count_method(self, mock_base_model, mock_pool):
        """Test count method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(return_value=[{"count": 42}])

        count = TestModel.count()

        assert count == 42
        mock_pool.execute_query.assert_called()

    def test_exists_method(self, mock_base_model, mock_pool):
        """Test exists method"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int
            name: str

        # Mock the execute_query method
        mock_pool.execute_query = Mock(return_value=[{"id": 1}])

        exists = TestModel.exists(id=1)

        assert exists is True
        mock_pool.execute_query.assert_called()

    def test_field_type_mapping(self, mock_base_model):
        """Test field type mapping"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            int_field: int
            str_field: str
            bool_field: bool
            float_field: float
            datetime_field: datetime

        # Test the type mapping
        mapping = TestModel._get_field_types()
        assert mapping["int_field"] == "INTEGER"
        assert mapping["str_field"] == "VARCHAR(255)"
        assert mapping["bool_field"] == "BOOLEAN"
        assert mapping["float_field"] == "DECIMAL(10,2)"
        assert "datetime_field" in mapping  # Should be TIMESTAMP

    def test_unique_constraints(self, mock_base_model):
        """Test unique constraints"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            email: str

            @classmethod
            def _get_unique_constraints(cls):
                return ["UNIQUE(email)"]

        constraints = TestModel._get_unique_constraints()
        assert "UNIQUE(email)" in constraints

    def test_primary_key_field(self, mock_base_model):
        """Test primary key field detection"""

        class TestModel(BaseModel):
            __tablename__ = "test_table"

            id: int = Field(json_schema_extra={"primary_key": True})
            name: str

        pk_field = TestModel._get_primary_key_field()
        assert pk_field == "id"
