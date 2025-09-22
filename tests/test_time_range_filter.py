"""Tests for TimeRangeFilter utility class."""

import pytest
from datetime import datetime
from dataclasses import dataclass
from typing import List

from elephant.utils.time_range_filter import TimeRangeFilter


@dataclass
class MockDataPoint:
    """Mock data point for testing."""

    time: datetime
    value: float


class TestTimeRangeFilter:
    """Tests for TimeRangeFilter utility class."""

    @pytest.fixture(name="sample_data")
    def fixture_sample_data(self) -> List[MockDataPoint]:
        """Sample time-series data for testing."""
        base_time = datetime.fromisoformat("2025-09-22T00:00:00+00:00")
        return [MockDataPoint(time=base_time.replace(hour=h), value=100.0 + h) for h in range(24)]

    def test_filter_strict_within_range(self, sample_data: List[MockDataPoint]) -> None:
        """Test strict filtering returns only data within the exact range."""
        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T12:00:00+00:00")

        result = TimeRangeFilter.filter_strict(sample_data, start_time, end_time)

        assert len(result) == 4  # Hours 8, 9, 10, 11
        assert all(start_time <= point.time < end_time for point in result)
        assert result[0].value == 108.0  # Hour 8
        assert result[3].value == 111.0  # Hour 11

    def test_filter_strict_outside_range(self, sample_data: List[MockDataPoint]) -> None:
        """Test strict filtering returns empty list when no data in range."""
        start_time = datetime.fromisoformat("2025-09-23T01:00:00+00:00")  # Next day
        end_time = datetime.fromisoformat("2025-09-23T05:00:00+00:00")

        result = TimeRangeFilter.filter_strict(sample_data, start_time, end_time)

        assert len(result) == 0

    def test_filter_strict_partial_overlap(self, sample_data: List[MockDataPoint]) -> None:
        """Test strict filtering with partial overlap."""
        start_time = datetime.fromisoformat("2025-09-22T22:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-23T02:00:00+00:00")  # Beyond available data

        result = TimeRangeFilter.filter_strict(sample_data, start_time, end_time)

        assert len(result) == 2  # Hours 22, 23
        assert result[0].value == 122.0  # Hour 22
        assert result[1].value == 123.0  # Hour 23

    def test_filter_strict_empty_data(self) -> None:
        """Test strict filtering with empty data list."""
        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T12:00:00+00:00")

        result: List[MockDataPoint] = TimeRangeFilter.filter_strict([], start_time, end_time)

        assert len(result) == 0

    def test_filter_with_interpolation_between_points(self, sample_data: List[MockDataPoint]) -> None:
        """Test interpolation mode returns bracketing points."""
        # Request data between 10:15 and 10:45 (should get 10:00 and 11:00)
        start_time = datetime.fromisoformat("2025-09-22T10:15:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T10:45:00+00:00")

        result = TimeRangeFilter.filter_with_interpolation(sample_data, start_time, end_time)

        assert len(result) == 2
        assert result[0].time == datetime.fromisoformat("2025-09-22T10:00:00+00:00")
        assert result[0].value == 110.0
        assert result[1].time == datetime.fromisoformat("2025-09-22T11:00:00+00:00")
        assert result[1].value == 111.0

    def test_filter_with_interpolation_overlapping_range(self, sample_data: List[MockDataPoint]) -> None:
        """Test interpolation mode with range that includes data points."""
        start_time = datetime.fromisoformat("2025-09-22T08:30:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T11:30:00+00:00")

        result = TimeRangeFilter.filter_with_interpolation(sample_data, start_time, end_time)

        # Should return: 08:00 (before), 09:00, 10:00, 11:00 (within), 12:00 (after)
        assert len(result) == 5
        assert result[0].time == datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        assert result[0].value == 108.0
        assert result[1].time == datetime.fromisoformat("2025-09-22T09:00:00+00:00")
        assert result[1].value == 109.0
        assert result[4].time == datetime.fromisoformat("2025-09-22T12:00:00+00:00")
        assert result[4].value == 112.0

    def test_filter_with_interpolation_no_before_point(self, sample_data: List[MockDataPoint]) -> None:
        """Test interpolation when no data point exists before start time."""
        start_time = datetime.fromisoformat("2025-09-21T22:00:00+00:00")  # Before any data
        end_time = datetime.fromisoformat("2025-09-22T02:00:00+00:00")

        result = TimeRangeFilter.filter_with_interpolation(sample_data, start_time, end_time)

        # Should return: 00:00, 01:00 (within), 02:00 (after)
        assert len(result) == 3
        assert result[0].time == datetime.fromisoformat("2025-09-22T00:00:00+00:00")
        assert result[2].time == datetime.fromisoformat("2025-09-22T02:00:00+00:00")

    def test_filter_with_interpolation_no_after_point(self, sample_data: List[MockDataPoint]) -> None:
        """Test interpolation when no data point exists after end time."""
        start_time = datetime.fromisoformat("2025-09-22T22:30:00+00:00")
        end_time = datetime.fromisoformat("2025-09-23T02:00:00+00:00")  # After all data

        result = TimeRangeFilter.filter_with_interpolation(sample_data, start_time, end_time)

        # Should return: 22:00 (before), 23:00 (within)
        assert len(result) == 2
        assert result[0].time == datetime.fromisoformat("2025-09-22T22:00:00+00:00")
        assert result[1].time == datetime.fromisoformat("2025-09-22T23:00:00+00:00")

    def test_filter_with_interpolation_empty_data(self) -> None:
        """Test interpolation with empty data list."""
        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T12:00:00+00:00")

        result: List[MockDataPoint] = TimeRangeFilter.filter_with_interpolation([], start_time, end_time)

        assert len(result) == 0

    def test_filter_with_interpolation_sorts_data(self) -> None:
        """Test that interpolation mode sorts unsorted data."""
        unsorted_data = [
            MockDataPoint(time=datetime.fromisoformat("2025-09-22T11:00:00+00:00"), value=111.0),
            MockDataPoint(time=datetime.fromisoformat("2025-09-22T09:00:00+00:00"), value=109.0),
            MockDataPoint(time=datetime.fromisoformat("2025-09-22T10:00:00+00:00"), value=110.0),
        ]

        start_time = datetime.fromisoformat("2025-09-22T09:30:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T10:30:00+00:00")

        result = TimeRangeFilter.filter_with_interpolation(unsorted_data, start_time, end_time)

        # Should return: 09:00 (before), 10:00 (within), 11:00 (after)
        assert len(result) == 3
        assert result[0].value == 109.0
        assert result[1].value == 110.0
        assert result[2].value == 111.0

    def test_filter_data_strict_mode(self, sample_data: List[MockDataPoint]) -> None:
        """Test filter_data convenience method in strict mode."""
        start_time = datetime.fromisoformat("2025-09-22T08:00:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T12:00:00+00:00")

        result = TimeRangeFilter.filter_data(sample_data, start_time, end_time, interpolate=False)

        assert len(result) == 4
        assert all(start_time <= point.time < end_time for point in result)

    def test_filter_data_interpolation_mode(self, sample_data: List[MockDataPoint]) -> None:
        """Test filter_data convenience method in interpolation mode."""
        start_time = datetime.fromisoformat("2025-09-22T10:15:00+00:00")
        end_time = datetime.fromisoformat("2025-09-22T10:45:00+00:00")

        result = TimeRangeFilter.filter_data(sample_data, start_time, end_time, interpolate=True)

        assert len(result) == 2
        assert result[0].time == datetime.fromisoformat("2025-09-22T10:00:00+00:00")
        assert result[1].time == datetime.fromisoformat("2025-09-22T11:00:00+00:00")
