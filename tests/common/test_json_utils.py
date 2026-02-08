"""
Tests for JustNews JSON Utilities
"""

import json
from datetime import date, datetime
from unittest.mock import Mock, patch

from common.json_utils import make_json_safe


class TestMakeJsonSafe:
    """Test make_json_safe function"""

    def test_primitive_types(self):
        """Test that primitive types pass through unchanged"""
        assert make_json_safe(None) is None
        assert make_json_safe("string") == "string"
        assert make_json_safe(42) == 42
        assert make_json_safe(3.14) == 3.14
        assert make_json_safe(True) is True
        assert make_json_safe(False) is False

    def test_bytes_conversion(self):
        """Test bytes to string conversion"""
        test_bytes = b"hello world"
        result = make_json_safe(test_bytes)
        assert result == "hello world"
        assert isinstance(result, str)

    def test_bytes_with_invalid_utf8(self):
        """Test bytes with invalid UTF-8 characters"""
        test_bytes = b"hello\xff\xfe world"
        result = make_json_safe(test_bytes)
        assert "hello" in result
        assert "world" in result
        assert isinstance(result, str)

    def test_datetime_conversion(self):
        """Test datetime to ISO format conversion"""
        dt = datetime(2023, 12, 25, 15, 30, 45)
        result = make_json_safe(dt)
        assert result == "2023-12-25T15:30:45"
        assert isinstance(result, str)

    def test_date_conversion(self):
        """Test date to ISO format conversion"""
        d = date(2023, 12, 25)
        result = make_json_safe(d)
        assert result == "2023-12-25"
        assert isinstance(result, str)

    def test_dict_conversion(self):
        """Test dictionary conversion with mixed types"""
        test_dict = {
            "string": "value",
            "number": 42,
            "datetime": datetime(2023, 1, 1),
            "bytes": b"data",
            "nested": {"key": "value", "date": date(2023, 1, 1)},
        }

        result = make_json_safe(test_dict)

        assert result["string"] == "value"
        assert result["number"] == 42
        assert result["datetime"] == "2023-01-01T00:00:00"
        assert result["bytes"] == "data"
        assert result["nested"]["key"] == "value"
        assert result["nested"]["date"] == "2023-01-01"

    def test_list_conversion(self):
        """Test list conversion with mixed types"""
        test_list = ["string", 42, datetime(2023, 1, 1), b"bytes", {"key": "value"}]

        result = make_json_safe(test_list)

        assert result[0] == "string"
        assert result[1] == 42
        assert result[2] == "2023-01-01T00:00:00"
        assert result[3] == "bytes"
        assert result[4]["key"] == "value"

    def test_set_conversion(self):
        """Test set conversion to list"""
        test_set = {1, 2, "three", datetime(2023, 1, 1)}

        result = make_json_safe(test_set)

        assert isinstance(result, list)
        assert len(result) == 4
        assert 1 in result
        assert 2 in result
        assert "three" in result
        assert "2023-01-01T00:00:00" in result

    def test_tuple_conversion(self):
        """Test tuple conversion to list"""
        test_tuple = ("a", 1, datetime(2023, 1, 1))

        result = make_json_safe(test_tuple)

        assert isinstance(result, list)
        assert result == ["a", 1, "2023-01-01T00:00:00"]

    def test_complex_object_conversion(self):
        """Test conversion of arbitrary objects to strings"""

        class CustomObject:
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return f"CustomObject({self.value})"

        obj = CustomObject("test")
        result = make_json_safe(obj)

        assert result == "CustomObject(test)"

    def test_depth_limit(self):
        """Test depth limit prevents infinite recursion"""
        # Create a self-referencing structure
        data = {}
        data["self"] = data

        result = make_json_safe(data, depth=30)

        # Should not crash and should return a string representation
        assert isinstance(result, str)

    def test_depth_limit_exact(self):
        """Test exact depth limit behavior"""
        # Create nested structure
        data = {"level": 0}
        current = data
        for i in range(35):  # Exceed depth limit
            current[f"level_{i}"] = {"value": i}
            current = current[f"level_{i}"]

        result = make_json_safe(data)

        # Should not crash - depth limit should prevent issues
        assert isinstance(result, dict)

    @patch("common.json_utils.lxml_etree")
    def test_lxml_element_conversion(self, mock_lxml):
        """Test lxml element conversion when lxml is available"""
        mock_lxml.tostring.return_value = "<element>content</element>"

        # Mock lxml element
        mock_element = Mock()
        mock_element.tag = "element"
        mock_element.attrib = {"class": "test"}

        result = make_json_safe(mock_element)

        assert result == "<element>content</element>"
        mock_lxml.tostring.assert_called_once()

    def test_lxml_element_conversion_no_lxml(self):
        """Test lxml element conversion when lxml is not available"""
        # When lxml_etree is None, should fall back to str()
        with patch("common.json_utils.lxml_etree", None):
            mock_element = Mock()
            mock_element.tag = "element"
            mock_element.attrib = {"class": "test"}

            result = make_json_safe(mock_element)

            assert "Mock object" in result or "element" in result

    @patch("common.json_utils.lxml_etree")
    def test_lxml_element_conversion_error(self, mock_lxml):
        """Test lxml element conversion when tostring fails"""
        mock_lxml.tostring.side_effect = Exception("Conversion failed")

        mock_element = Mock()
        mock_element.tag = "element"
        mock_element.attrib = {"class": "test"}

        result = make_json_safe(mock_element)

        # Should fall back to str() representation
        assert isinstance(result, str)

    def test_json_serializable_output(self):
        """Test that output is actually JSON serializable"""
        complex_data = {
            "datetime": datetime(2023, 1, 1, 12, 0, 0),
            "bytes": b"test data",
            "set": {1, 2, 3},
            "nested": {
                "date": date(2023, 1, 1),
                "custom": object(),  # This will become a string
            },
        }

        result = make_json_safe(complex_data)

        # Should be able to serialize to JSON without errors
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

        # Verify we can parse it back
        parsed = json.loads(json_str)
        assert parsed["datetime"] == "2023-01-01T12:00:00"
        assert parsed["bytes"] == "test data"
        assert isinstance(parsed["set"], list)
        assert set(parsed["set"]) == {1, 2, 3}
        assert parsed["nested"]["date"] == "2023-01-01"
        assert isinstance(parsed["nested"]["custom"], str)

    def test_empty_containers(self):
        """Test handling of empty containers"""
        assert make_json_safe({}) == {}
        assert make_json_safe([]) == []
        assert make_json_safe(set()) == []
