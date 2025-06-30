# Revised Implementation Approach - Minimal Dependencies

## Overview

Based on the constraints:
- Limited ability to add packages
- No ORM (direct SQL only)
- Oracle database instead of PostgreSQL
- Minimal external dependencies

## Revised Implementation Strategy

### 1. Database Abstraction - Using Only cx_Oracle

Instead of SQLAlchemy ORM, we'll create a lightweight abstraction:

```python
# db/interfaces/database_interface.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import sqlite3

class DatabaseInterface(ABC):
    @abstractmethod
    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        pass
    
    @abstractmethod
    def fetchone(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict]:
        pass
    
    @abstractmethod
    def fetchall(self, query: str, params: Optional[Tuple] = None) -> List[Dict]:
        pass

# db/adapters/sqlite_adapter.py
class SQLiteAdapter(DatabaseInterface):
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                return cursor.execute(query, params)
            return cursor.execute(query)

# db/adapters/oracle_adapter.py
class OracleAdapter(DatabaseInterface):
    def __init__(self, dsn: str, user: str, password: str):
        import cx_Oracle
        self.dsn = dsn
        self.user = user
        self.password = password
        
    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        import cx_Oracle
        with cx_Oracle.connect(self.user, self.password, self.dsn) as conn:
            cursor = conn.cursor()
            if params:
                return cursor.execute(query, params)
            return cursor.execute(query)
```

### 2. Configuration Management - Using Only JSON (stdlib)

No Pydantic needed - just use stdlib json and custom validation:

```python
# config/validator.py
import json
from typing import Dict, List, Tuple, Any

class ConfigValidator:
    @staticmethod
    def validate_job_config(job: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        
        # Required fields
        if 'id' not in job:
            errors.append("Job missing required field 'id'")
        if 'command' not in job:
            errors.append("Job missing required field 'command'")
        
        # Type validation
        if 'timeout' in job and not isinstance(job['timeout'], (int, float)):
            errors.append(f"Job {job.get('id', 'unknown')}: timeout must be numeric")
        
        # Range validation
        if 'timeout' in job and job['timeout'] <= 0:
            errors.append(f"Job {job.get('id', 'unknown')}: timeout must be positive")
        
        return len(errors) == 0, errors
```

### 3. Structured Logging - Using Only stdlib

Create our own structured logging without external packages:

```python
# executioner_logging/structured.py
import json
import logging
from datetime import datetime
from typing import Dict, Any

class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, 'job_id'):
            log_data['job_id'] = record.job_id
        if hasattr(record, 'run_id'):
            log_data['run_id'] = record.run_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

# Usage
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.addHandler(handler)

# Log with structure
logger.info("Job started", extra={'job_id': 'job1', 'run_id': 42})
```

### 4. Type Hints - Using Only typing_extensions

This is a small package that just extends stdlib typing:

```python
# For Python 3.6 compatibility
try:
    from typing import Protocol  # Python 3.8+
except ImportError:
    from typing_extensions import Protocol  # Backport

# Define protocols for better type safety
class Executable(Protocol):
    def execute(self, command: str, timeout: int) -> Tuple[int, str, str]:
        ...
```

### 5. Metrics Collection - Using Only stdlib

Create simple metrics without Prometheus:

```python
# monitoring/metrics.py
import time
import json
from collections import defaultdict
from typing import Dict, List
import threading

class MetricsCollector:
    def __init__(self):
        self._metrics = defaultdict(list)
        self._lock = threading.Lock()
    
    def record_job_duration(self, job_id: str, duration: float):
        with self._lock:
            self._metrics['job_durations'].append({
                'job_id': job_id,
                'duration': duration,
                'timestamp': time.time()
            })
    
    def export_json(self) -> str:
        with self._lock:
            return json.dumps(dict(self._metrics), indent=2)
    
    def export_for_monitoring(self) -> Dict[str, float]:
        """Export in a format that monitoring tools can scrape"""
        with self._lock:
            stats = {}
            
            # Calculate averages
            durations = self._metrics.get('job_durations', [])
            if durations:
                stats['avg_job_duration'] = sum(d['duration'] for d in durations) / len(durations)
                stats['max_job_duration'] = max(d['duration'] for d in durations)
                stats['min_job_duration'] = min(d['duration'] for d in durations)
            
            return stats
```

### 6. API Layer - Using Only stdlib

If API is needed, use stdlib's http.server:

```python
# api/simple_api.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse

class ExecutionerAPIHandler(BaseHTTPRequestHandler):
    def __init__(self, executioner_instance, *args, **kwargs):
        self.executioner = executioner_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            status = {
                'running': True,
                'current_run_id': self.executioner.current_run_id,
                'jobs_completed': len(self.executioner.completed_jobs)
            }
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/submit':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            config = json.loads(post_data)
            
            # Validate and submit
            run_id = self.executioner.submit_config(config)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'run_id': run_id}).encode())
```

## What We Can Implement Without Additional Packages

### ✅ Can Implement with stdlib + cx_Oracle:

1. **Database Abstraction** - Direct SQL, no ORM
2. **Type Safety** - Using typing_extensions only
3. **Structured Logging** - JSON formatting with stdlib
4. **Configuration Validation** - Custom validators
5. **Dependency Injection** - Simple factory pattern
6. **State Management** - Using dictionaries and locks
7. **Error Handling** - Custom exception hierarchy
8. **Simple API** - http.server from stdlib
9. **Metrics** - JSON export, file-based
10. **Testing** - pytest (already approved)

### ❌ Cannot Implement without packages:

1. **Async/await execution** - Would need aiofiles, etc.
2. **Advanced API features** - No OpenAPI/Swagger
3. **Prometheus metrics** - Custom format instead
4. **PostgreSQL support** - Oracle only
5. **Advanced monitoring** - Basic metrics only

## Oracle-Specific Considerations

### Connection Management

```python
# db/oracle_utils.py
import cx_Oracle

class OracleConnectionPool:
    def __init__(self, user: str, password: str, dsn: str, min_size: int = 2, max_size: int = 10):
        self.pool = cx_Oracle.SessionPool(
            user=user,
            password=password,
            dsn=dsn,
            min=min_size,
            max=max_size,
            increment=1
        )
    
    def get_connection(self):
        return self.pool.acquire()
    
    def close(self):
        self.pool.close()
```

### Schema Modifications for Oracle

```sql
-- Oracle-specific schema
CREATE TABLE job_history (
    run_id NUMBER NOT NULL,
    id VARCHAR2(255) NOT NULL,
    description VARCHAR2(4000),
    command VARCHAR2(4000),
    status VARCHAR2(50),
    application_name VARCHAR2(255),
    last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_seconds NUMBER,
    retry_count NUMBER DEFAULT 0,
    CONSTRAINT pk_job_history PRIMARY KEY (run_id, id)
);

CREATE INDEX idx_job_history_run_id ON job_history(run_id);
CREATE INDEX idx_job_history_status ON job_history(status);

-- Sequence for run IDs
CREATE SEQUENCE run_id_seq START WITH 1 INCREMENT BY 1;
```

## Implementation Priority with Minimal Packages

### Phase 1: Core Improvements (No new packages)
1. Better error handling with custom exceptions
2. Structured logging using stdlib
3. Type hints with typing_extensions
4. Improved configuration validation

### Phase 2: Database Abstraction (cx_Oracle only)
1. Create database interface
2. Implement SQLite adapter (current)
3. Implement Oracle adapter
4. Migration scripts for Oracle

### Phase 3: Monitoring & API (No new packages)
1. Simple metrics collection
2. JSON export for monitoring
3. Basic HTTP API using stdlib
4. File-based state management

## Benefits of This Approach

1. **Minimal Dependencies** - Only cx_Oracle needed
2. **No ORM Overhead** - Direct SQL control
3. **Oracle Native Features** - Can use PL/SQL, advanced features
4. **Easier Approval** - Fewer packages to review
5. **Smaller Footprint** - ~10MB vs ~185MB

## Trade-offs

1. **More Code to Write** - No framework conveniences
2. **Less Features** - No automatic API docs, etc.
3. **Manual SQL** - Need to write all queries
4. **Basic Monitoring** - No Prometheus integration
5. **Limited Async** - Stuck with threading model

This approach gives you most of the architectural improvements while respecting your constraints!