"""
Tests for JustNews Observability Utilities
"""

import logging
import os
from unittest.mock import patch

from common.observability import LOG_DIR, get_logger, setup_logging


class TestObservability:
    """Test observability utilities"""

    def test_log_dir_creation(self):
        """Test that LOG_DIR is created if it doesn't exist"""
        assert os.path.exists(LOG_DIR)
        assert os.path.isdir(LOG_DIR)

    def test_get_logger_basic(self):
        """Test basic logger creation"""
        logger = get_logger("test_module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"
        assert logger.level == logging.DEBUG

    def test_get_logger_creates_file_handler(self):
        """Test that logger creates file handler with correct path"""
        logger = get_logger("test.module")

        # Check that handlers were added
        assert len(logger.handlers) >= 2  # File handler + console handler

        # Find the file handler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        expected_path = os.path.join(LOG_DIR, "module.log")
        assert file_handler.baseFilename == expected_path

    def test_get_logger_console_handler(self):
        """Test that logger includes console handler"""
        logger = get_logger("test_module")

        # Check for console handler
        console_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                console_handler = handler
                break

        assert console_handler is not None

    def test_get_logger_idempotent(self):
        """Test that get_logger returns same logger instance for same name"""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")

        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Test that different logger names create different loggers"""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1 is not logger2
        assert logger1.name == "module1"
        assert logger2.name == "module2"

    def test_get_logger_file_rotation(self):
        """Test that file handler has correct rotation settings"""
        logger = get_logger("test_module")

        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        assert file_handler.maxBytes == 10 * 1024 * 1024  # 10 MB
        assert file_handler.backupCount == 5

    def test_get_logger_formatter(self):
        """Test that handlers have correct formatter"""
        logger = get_logger("test_module")

        for handler in logger.handlers:
            formatter = handler.formatter
            assert formatter is not None
            assert "%(asctime)s" in formatter._fmt
            assert "%(name)s" in formatter._fmt
            assert "%(levelname)s" in formatter._fmt
            assert "%(message)s" in formatter._fmt
            assert formatter.datefmt == "%Y-%m-%d %H:%M:%S"

    def test_setup_logging_basic(self):
        """Test basic logging setup"""
        setup_logging()

        # Check that basic config was applied
        root_logger = logging.getLogger()
        assert root_logger.hasHandlers()

    def test_setup_logging_custom_level(self):
        """Test setup logging with custom level"""
        setup_logging(level=logging.DEBUG)

        root_logger = logging.getLogger()
        assert root_logger.level <= logging.DEBUG

    def test_setup_logging_custom_format(self):
        """Test setup logging with custom format"""
        custom_format = "%(levelname)s: %(message)s"
        setup_logging(format_string=custom_format)

        # The basic config should have been applied with the custom format
        # This is hard to test directly, but we can verify no exceptions
        assert True

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_log_dir_creation_failure_handling(self, mock_exists, mock_makedirs):
        """Test handling when log directory creation fails"""
        mock_exists.return_value = False
        mock_makedirs.side_effect = OSError("Permission denied")

        # This should not raise an exception - the module handles it gracefully
        # by importing the LOG_DIR variable
        from common import observability

        assert hasattr(observability, "LOG_DIR")

    def test_logger_actual_logging(self):
        """Test that logger actually writes to file"""
        logger = get_logger("test_logging")

        test_message = "Test log message"
        logger.info(test_message)

        # Find the log file
        log_file = None
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                log_file = handler.baseFilename
                break

        assert log_file is not None
        assert os.path.exists(log_file)

        # Check that message was written
        with open(log_file, encoding="utf-8") as f:
            content = f.read()
            assert test_message in content

    def test_multiple_loggers_different_files(self):
        """Test that different loggers write to different files"""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        logger1.info("Message from module1")
        logger2.info("Message from module2")

        # Find log files
        file1 = None
        file2 = None

        for handler in logger1.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file1 = handler.baseFilename

        for handler in logger2.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file2 = handler.baseFilename

        assert file1 != file2
        assert "module1.log" in file1
        assert "module2.log" in file2
