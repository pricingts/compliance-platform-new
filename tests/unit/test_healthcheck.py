"""Tests for health check endpoint."""
import pytest
from unittest.mock import patch, MagicMock


class TestHealthCheck:
    def test_check_db_connection_success(self):
        """check_db should return True when DB is reachable."""
        from healthcheck import check_db

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = MagicMock()

        with patch("healthcheck._get_engine", return_value=mock_engine):
            assert check_db() is True

    def test_check_db_connection_failure(self):
        """check_db should return False when DB is unreachable."""
        from healthcheck import check_db

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection refused")

        with patch("healthcheck._get_engine", return_value=mock_engine):
            assert check_db() is False

    def test_health_status_healthy(self):
        """health_status should return healthy dict when all checks pass."""
        from healthcheck import health_status

        with patch("healthcheck.check_db", return_value=True):
            result = health_status()
            assert result["status"] == "healthy"
            assert result["database"] is True

    def test_health_status_unhealthy(self):
        """health_status should return unhealthy dict when checks fail."""
        from healthcheck import health_status

        with patch("healthcheck.check_db", return_value=False):
            result = health_status()
            assert result["status"] == "unhealthy"
            assert result["database"] is False
