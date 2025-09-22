"""Time range filtering utilities for time-series data."""

from typing import List, TypeVar, Protocol
from datetime import datetime


class TimeSeriesDataPoint(Protocol):
    """Protocol for objects with a time attribute."""

    time: datetime


T = TypeVar("T", bound=TimeSeriesDataPoint)


class TimeRangeFilter:
    """Utility class for filtering time-series data by time ranges."""

    @staticmethod
    def filter_strict(data: List[T], start_time: datetime, end_time: datetime) -> List[T]:
        """
        Filter data to only include points within the exact time range.

        Args:
            data: List of time-series data points
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive)

        Returns:
            List of data points where start_time <= point.time < end_time
        """
        results = []
        for data_point in data:
            if start_time <= data_point.time < end_time:
                results.append(data_point)
        return results

    @staticmethod
    def filter_with_interpolation(data: List[T], start_time: datetime, end_time: datetime) -> List[T]:
        """
        Filter data to include points that bracket or overlap the requested time range.

        This method includes:
        - The last data point before start_time (for interpolation)
        - All data points within the time range
        - The first data point after end_time (for interpolation)

        Args:
            data: List of time-series data points (will be sorted by time)
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive)

        Returns:
            List of data points useful for interpolation within the time range
        """
        if not data:
            return []

        # Sort by time to ensure correct ordering
        sorted_data = sorted(data, key=lambda x: x.time)
        results = []

        # Find the last data point before start_time (for interpolation)
        before_start = None
        for data_point in sorted_data:
            if data_point.time < start_time:
                before_start = data_point
            else:
                break

        # Add the bracketing point before start_time if it exists
        if before_start:
            results.append(before_start)

        # Add all data points within the requested range
        for data_point in sorted_data:
            if start_time <= data_point.time < end_time:
                results.append(data_point)

        # Find the first data point after end_time (for interpolation)
        for data_point in sorted_data:
            if data_point.time >= end_time:
                results.append(data_point)
                break

        return results

    @staticmethod
    def filter_data(data: List[T], start_time: datetime, end_time: datetime, interpolate: bool = False) -> List[T]:
        """
        Filter time-series data based on the specified mode.

        Args:
            data: List of time-series data points
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive)
            interpolate: If True, include bracketing points for interpolation

        Returns:
            Filtered list of data points
        """
        if interpolate:
            return TimeRangeFilter.filter_with_interpolation(data, start_time, end_time)
        else:
            return TimeRangeFilter.filter_strict(data, start_time, end_time)
