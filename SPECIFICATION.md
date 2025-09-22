# Elephant Service Specification

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| **API Endpoints** | | |
| `GET /carbon-intensity/current` | ✅ **Implemented** | Full validation, error handling |
| `GET /carbon-intensity/history` | ✅ **Implemented** | Full validation, error handling |
| `POST /simulation/timepoints` | ❌ **Not Implemented** | Core simulation feature |
| `POST /simulation/ranges` | ❌ **Not Implemented** | Core simulation feature |
| `GET /simulation/{sessionId}` | ❌ **Not Implemented** | Core simulation feature |
| `GET /simulation/{sessionId}/current` | ❌ **Not Implemented** | Core simulation feature |
| `GET /simulations` | ❌ **Not Implemented** | Management feature |
| `GET /health` | ✅ **Implemented** | Basic health check |
| **Data Providers** | | |
| ElectricityMaps Integration | ✅ **Implemented** | Full API integration, error handling |
| Carbon-Aware-SDK Support | ❌ **Not Implemented** | Planned for future |
| Carbon-Aware-Computing Support | ❌ **Not Implemented** | Planned for future |
| **Configuration** | | |
| YAML Configuration Loading | ✅ **Implemented** | Provider-specific validation |
| Startup Validation | ✅ **Implemented** | Graceful handling of missing providers |
| Provider Token Validation | ✅ **Implemented** | Provider-specific requirements |
| **Core Features** | | |
| FastAPI Application | ✅ **Implemented** | With lifecycle management |
| Data Models & Validation | ✅ **Implemented** | Pydantic v2, carbon intensity bounds |
| Error Handling | ✅ **Implemented** | Proper HTTP status codes, provider errors |
| **Simulation Engine** | | |
| Session Management | ❌ **Not Implemented** | Core differentiator |
| Time Points Simulation | ❌ **Not Implemented** | Core differentiator |
| Time Ranges Simulation | ❌ **Not Implemented** | Core differentiator |
| Real-time Playback | ❌ **Not Implemented** | Core differentiator |
| **Testing & Quality** | | |
| Unit Tests | ✅ **Implemented** | multiple tests added, all passing |
| Configuration Tests | ✅ **Implemented** | Provider validation |
| API Integration Tests | ✅ **Implemented** | Endpoint validation |
| **Deployment** | | |
| Docker Support | ✅ **Implemented** | See `Dockerfile` |
| Example Configuration | ✅ **Implemented** | `config.example.yml` |

**Legend:**

- ✅ **Implemented**: Feature is complete and tested
- 🟡 **Partial**: Feature is partially implemented
- ❌ **Not Implemented**: Feature is planned but not started

## Overview

**Elephant** is a specialized dockerized Carbon Grid Intensity (CGI) service focused on **simulation capabilities** for carbon intensity scenarios. While it can provide current and historical carbon intensity data from multiple providers, its primary differentiator is the advanced simulation functionality for testing and modeling carbon-aware computing scenarios.

### Purpose

Elephant will be integrated with the Green Metrics Tool (GMT) to provide dynamic carbon intensity values with powerful simulation features. Unlike existing carbon intensity facades, Elephant's core value proposition is enabling users to create, store, and replay custom carbon intensity scenarios for testing and development.

## Technical Requirements

### Runtime Environment

- **Language**: Python 3.10
- **Framework**: FastAPI
- **Deployment**: Docker container
- **Data Storage**: In-memory (Redis for future database caching if needed)
- **Configuration**: YAML file only
- **Time Zone**: All timestamps in UTC

## API Endpoints

The API follows the Carbon-Aware-Computing.com structure for simplicity and consistency.

### 1. Get Current Carbon Grid Intensity

```plain
GET /carbon-intensity/current
```

**Query Parameters:**

- `location` (required): Country code (e.g., "DE", "US")

**Response:**

```json
{
  "location": "DE",
  "time": "2025-09-22T10:45:00+00:00",
  "carbonIntensity": 241
}
```

### 2. Get Historical Carbon Grid Intensity

```plain
GET /carbon-intensity/history
```

**Query Parameters:**

- `location` (required): Country code
- `startTime` (required): ISO 8601 timestamp
- `endTime` (required): ISO 8601 timestamp

**Response:**

```json
[
  {
    "location": "DE",
    "time": "2025-09-22T10:00:00+00:00",
    "carbonIntensity": 241
  },
  {
    "location": "DE",
    "time": "2025-09-22T11:00:00+00:00",
    "carbonIntensity": 235
  }
]
```

### 3. Create Simulation Request ⭐ **CORE FEATURE**

**Elephant's primary differentiator** - Create custom carbon intensity scenarios for testing and modeling.

#### Endpoint A: Time-Value Pairs

```plain
POST /simulation/timepoints
```

**Request Body:**

```json
{
  "description": "Peak usage simulation",
  "data": [
    [1, 150],    // At 1 second: CGI = 150
    [30, 200],   // At 30 seconds: CGI = 200
    [60, 300],   // At 60 seconds: CGI = 300
    [120, 100]   // At 120 seconds: CGI = 100
  ]
}
```

#### Endpoint B: Time Ranges

```plain
POST /simulation/ranges
```

**Request Body:**

```json
{
  "description": "Daily cycle simulation",
  "ranges": [
    [0, 3600, 150],      // 0-1 hour: CGI = 150
    [3601, 7200, 200],   // 1-2 hours: CGI = 200
    [7201, 10800, 300]   // 2-3 hours: CGI = 300
  ]
}
```

**Response (both endpoints):**

```json
{
  "sessionId": "uuid-string",
  "description": "Peak usage simulation",
  "createdAt": "2025-09-22T10:45:00+00:00",
  "expiresAt": "2025-09-22T11:45:00+00:00",
  "dataPoints": 4
}
```

### 4. Get Simulation Data ⭐ **CORE FEATURE**

**Retrieve and replay simulation scenarios** - This is what makes Elephant unique.

```plain
GET /simulation/{sessionId}
```

**Response:**

```json
{
  "sessionId": "uuid-string",
  "description": "Peak usage simulation",
  "data": [[1, 150], [30, 200], [60, 300], [120, 100]],
  "createdAt": "2025-09-22T10:45:00+00:00",
  "expiresAt": "2025-09-22T11:45:00+00:00",
  "status": "active"
}
```

### 5. Get Current Simulation Value ⭐ **CORE FEATURE**

**Real-time simulation playback** - Get the current CGI value based on elapsed time since simulation start.

```plain
GET /simulation/{sessionId}/current?elapsed={seconds}
```

**Query Parameters:**

- `elapsed` (required): Seconds elapsed since simulation start

**Response:**

```json
{
  "sessionId": "uuid-string",
  "elapsed": 45,
  "location": "simulation",
  "time": "2025-09-22T10:45:45+00:00",
  "value": 200
}
```

**Logic**: For elapsed=45s with data `[[1,150],[30,200],[60,300],[120,100]]`, return 200 (value at 30s, as it's the latest timepoint ≤ 45s).

### 6. List Active Simulations ⭐ **MANAGEMENT FEATURE**

```plain
GET /simulations
```

**Response:**

```json
{
  "simulations": [
    {
      "sessionId": "uuid-1",
      "description": "Peak usage simulation",
      "createdAt": "2025-09-22T10:45:00+00:00",
      "expiresAt": "2025-09-22T11:45:00+00:00",
      "dataPoints": 4,
      "status": "active"
    }
  ],
  "total": 1
}
```

## Data Providers

### Primary Implementation: ElectricityMaps

- **Base URL**: <https://api.electricitymaps.com>
- **Endpoints**:
  - `/v3/carbon-intensity/latest`
  - `/v3/carbon-intensity/history`
- **Authentication**: API Token
- **Documentation**: <https://portal.electricitymaps.com/developer-hub/api/getting-started>

**Sample Request:**

```sh
curl "https://api.electricitymaps.com/v3/carbon-intensity/latest?zone=DE" -H "auth-token: $AUTH_TOKEN"
```

**Sample Response:**

```json
{
  "zone": "DE",
  "carbonIntensity": 241,
  "datetime": "2025-09-22T08:00:00.000Z",
  "updatedAt": "2025-09-22T07:55:51.863Z",
  "createdAt": "2025-09-19T21:26:02.144Z",
  "emissionFactorType": "lifecycle",
  "isEstimated": true,
  "estimationMethod": "FORECASTS_HIERARCHY",
  "temporalGranularity": "hourly"
}
```

### Future Providers (Facade Support)

#### Carbon-Aware-SDK

- **Deployment**: Locally hosted
- **Base URL**: Configurable
- **Documentation**: <https://carbon-aware-sdk.greensoftware.foundation/docs/tutorial-basics/carbon-aware-webapi>

**Sample Response:**

```json
{
  "location": "eastus",
  "startTime": "2022-03-01T15:30:00Z",
  "endTime": "2022-03-01T18:30:00Z",
  "carbonIntensity": 345.434
}
```

**Error Response:**

```json
{
  "type": "string",
  "title": "string",
  "status": 0,
  "detail": "string",
  "instance": "string",
  "errors": {
    "additionalProp1": ["string"]
  }
}
```

#### Carbon-Aware-Computing

- **Base URL**: <https://intensity.carbon-aware-computing.com>
- **Documentation**:
  - Swagger UI: <https://intensity.carbon-aware-computing.com/swagger/UI>
  - OpenAPI: <https://intensity.carbon-aware-computing.com/swagger.json>

**Sample Response:**

```json
{
  "location": "de",
  "time": "2025-09-22T10:45:00+00:00",
  "value": 270.9
}
```

## Configuration

### YAML Configuration File (`config.yml`)

**Setup**: Copy `config.example.yml` to `config.yml` and fill in your API tokens.

```yaml
# Provider configuration
providers:
  electricitymaps:
    enabled: true
    base_url: "https://api.electricitymaps.com"
    api_token: "your-electricitymaps-api-token-here"

  carbon_aware_sdk:
    enabled: false
    base_url: "http://localhost:8080"
    api_token: null  # No token needed for local deployment

  carbon_aware_computing:
    enabled: false
    base_url: "https://intensity.carbon-aware-computing.com"
    api_token: "your-carbon-aware-computing-api-token-here"

# Background polling configuration
polling:
  enabled: true
  interval_minutes: 5  # Default: 5 minutes

# Data retention
cache:
  retention_hours: 24  # Default: 1 day

# Simulation settings
simulation:
  session_expiry_hours: 1
  max_data_points: 1000        # Maximum data points per simulation
  max_concurrent_sessions: 100  # Maximum concurrent sessions
  time_unit: "seconds"
  cleanup_interval_minutes: 15  # How often to clean expired sessions

# Logging
logging:
  level: "INFO"
```

## Background Processing

### Periodic Data Polling

- **Purpose**: Continuously fetch current carbon intensity data to build historical cache
- **Frequency**: Configurable (default: 5 minutes)
- **Behavior**: Poll all enabled providers for current data
- **Error Handling**: Log errors, continue polling other providers

### Data Caching Strategy

- **Storage**: In-memory cache
- **Retention**: Configurable (default: 24 hours)
- **Key Structure**: `{provider}:{location}:{timestamp}`
- **Cleanup**: Automatic cleanup of expired data

## ⭐ SIMULATION ENGINE

**Elephant's primary value proposition** lies in its simulation capabilities, enabling developers and researchers to create, manage, and replay custom carbon intensity scenarios.

### Simulation Use Cases

1. **Testing Carbon-Aware Applications**: Test how applications behave under different carbon intensity patterns
2. **Research & Modeling**: Model carbon intensity scenarios for specific regions or time periods
3. **Development & Debugging**: Reproducible carbon intensity patterns for consistent testing
4. **What-If Analysis**: Explore how different carbon intensity profiles affect application behavior
5. **Benchmarking**: Compare application performance under controlled carbon intensity conditions

### Simulation Types

#### Type 1: Discrete Time Points

Perfect for **event-driven scenarios** or **specific measurement points**.

```json
{
  "data": [
    [0, 150],     // Start: 150 gCO2/kWh
    [30, 200],    // At 30s: spike to 200 gCO2/kWh
    [60, 100],    // At 60s: drop to 100 gCO2/kWh
    [120, 300]    // At 120s: peak at 300 gCO2/kWh
  ]
}
```

**Behavior**: Value remains constant until next timepoint. Between timepoints, the previous value is used.

#### Type 2: Time Ranges

Perfect for **continuous periods** or **steady-state scenarios**.

```json
{
  "ranges": [
    [0, 1800, 150],       // First 30 min: 150 gCO2/kWh
    [1801, 3600, 200],    // Next 30 min: 200 gCO2/kWh
    [3601, 5400, 250]     // Final 30 min: 250 gCO2/kWh
  ]
}
```

**Behavior**: Explicit ranges with defined start/end times. No gaps allowed.

### Session Management

#### Session Lifecycle

1. **Creation**: POST to `/simulation/timepoints` or `/simulation/ranges`
2. **Active Period**: 1 hour lifespan with full read access
3. **Expiry**: Automatic cleanup after expiration
4. **Concurrent Support**: Multiple active sessions per user/system

#### Session Data Structure

```python
class SimulationSession:
    session_id: str (UUID4)
    description: str
    simulation_type: "timepoints" | "ranges"
    data: List[List[int|float]]  # [[time, value], ...] or [[start, end, value], ...]
    created_at: datetime (UTC)
    expires_at: datetime (UTC, +1 hour)
    access_count: int
    last_accessed: datetime (UTC)
```

### Real-Time Playback Algorithm

#### For Time Points Data

```python
def get_simulation_value(data: List[List], elapsed_seconds: int) -> float:
    # Find the latest timepoint <= elapsed_seconds
    applicable_points = [(t, v) for t, v in data if t <= elapsed_seconds]
    if not applicable_points:
        return data[0][1]  # Return first value if elapsed < first timepoint
    return max(applicable_points)[1]  # Return value of latest applicable timepoint
```

#### For Time Ranges Data

```python
def get_simulation_value(ranges: List[List], elapsed_seconds: int) -> float:
    # Find the range that contains elapsed_seconds
    for start, end, value in ranges:
        if start <= elapsed_seconds <= end:
            return value
    # Handle edge cases (before first range, after last range)
    return ranges[0][2] if elapsed_seconds < ranges[0][0] else ranges[-1][2]
```

### Advanced Simulation Features

#### Session Metadata & Analytics

- Track access patterns and usage statistics
- Optional description field for documentation
- Creation timestamp and expiry management
- Data point count for quick validation

#### Validation & Error Handling

- **Time Point Validation**:
  - Ensure chronological order
  - **Duplicate timestamps**: Return HTTP 400 Bad Request error
- **Range Validation**: No overlaps, no gaps, chronological order
- **Value Validation**:
  - Carbon intensity values must be between **0-1000 gCO2/kWh**
  - Return HTTP 400 Bad Request for values outside this range
- **Size Limits**: Maximum data points per simulation (configurable)
- **Elapsed Time Validation**:
  - If `elapsed` time exceeds last defined timepoint/range: Return HTTP 400 Bad Request
  - Include clear error message indicating valid time range

#### Session Discovery

- List all active sessions with metadata
- Filter by creation date, expiry status, or description
- Quick stats: total sessions, total data points, memory usage

## Provider Facade Pattern

### Interface Design

```python
class CarbonIntensityProvider:
    def get_current(self, location: str) -> CarbonIntensityData
    def get_historical(self, location: str, start_time: datetime, end_time: datetime) -> List[CarbonIntensityData]
```

### Data Normalization

All provider responses normalized to:

```python
class CarbonIntensityData:
    location: str
    time: datetime  # UTC
    carbon_intensity: float
```

## Error Handling

### Startup Validation

- **Application MUST fail to start** if configuration is invalid:
  - No providers enabled
  - Missing required API tokens for enabled providers
  - Invalid base URLs or malformed configuration

### Provider Failures

- **Graceful Degradation**: When providers are temporarily unavailable:
  - Return HTTP 503 Service Unavailable with appropriate error message
  - Log errors for monitoring
  - Continue serving simulation endpoints (unaffected by provider status)

### Rate Limiting

- **Behavior**: Requests exceeding provider rate limits are **rejected**
- Return HTTP 429 Too Many Requests
- No request queuing or retry mechanisms

### HTTP Status Codes

- `200`: Success
- `400`: Bad Request (invalid parameters)
- `404`: Not Found (invalid session ID)
- `500`: Internal Server Error (provider failures)

## Docker Configuration

Dockerfile Requirements:

- Use a current slim Python image as base
- All configuration via YAML file (no environment variables needed)
- Default config path: `/app/config.yml`

## Dependencies

### Core Dependencies

- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `httpx`: HTTP client for external APIs
- `pydantic`: Data validation
- `pyyaml`: YAML configuration parsing
- `python-multipart`: For POST request handling

### Development Dependencies

- `pytest`: Testing framework
- `pytest-asyncio`: Async testing support
- `httpx`: Test client

## Location Format

### Current Implementation

- **Format**: Country codes (ISO 3166-1 alpha-2) only
- **Examples**: "DE", "US", "FR"
- **Provider Mapping**: Elephant handles conversion between country codes and provider-specific formats

### Future Enhancement

- **Cloud Region Support**: Region names (e.g., "eastus", "eu-west-1") will be supported in future versions
- **Automatic Mapping**: Cloud regions will automatically map to corresponding country codes
- **Backward Compatibility**: Country code format will remain supported

## Future Considerations

### Database Integration

- **Redis** for persistent caching when scaling beyond in-memory storage
- Session persistence across service restarts
- Distributed simulation sessions

### Enhanced Simulation Features

- **Simulation Templates**: Pre-defined common carbon intensity patterns
- **Interpolation**: Smooth transitions between time points
- **Looping**: Repeatable simulation cycles
- **Real-time Streaming**: WebSocket support for live simulation updates

### Location Format Harmonization

- Future enhancement to support multiple location formats
- Mapping between provider-specific location identifiers

### Enhanced Rate Limiting

- Monitor provider API rate limits
- Implement client-side rate limiting if needed

### Monitoring & Metrics

- Health check endpoints
- Provider availability metrics
- Cache hit/miss ratios
