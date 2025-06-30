# Executioner Architecture Improvements Implementation Plan

## Overview

This document provides a detailed implementation plan for modernizing the Executioner architecture. Each improvement is broken down into phases with specific tasks, dependencies, and estimated effort.

## Python 3.6 Compatibility Requirement

**IMPORTANT**: All implementations MUST maintain compatibility with Python 3.6 as the minimum supported version. This affects several modern Python features and requires careful consideration throughout the implementation.

### Key Compatibility Guidelines:
- Use `typing_extensions` for advanced type hints not available in Python 3.6
- Use `dataclasses` backport for Python < 3.7
- Avoid Python 3.7+ exclusive features (walrus operator, positional-only parameters, pattern matching)
- Test all code on Python 3.6 before committing
- Use conditional imports where necessary for version-specific features

## Table of Contents

1. [Database Design & Scalability](#1-database-design--scalability)
2. [Separation of Concerns](#2-separation-of-concerns)
3. [Error Handling & Observability](#3-error-handling--observability)
4. [Testing & Dependency Injection](#4-testing--dependency-injection)
5. [Async/Await Implementation](#5-asyncawait-implementation)
6. [Configuration Management](#6-configuration-management)
7. [State Management](#7-state-management)
8. [API-First Design](#8-api-first-design)
9. [Resource Management](#9-resource-management)
10. [Modern Python Features](#10-modern-python-features)
11. [Implementation Timeline](#implementation-timeline)
12. [Python 3.6 Compatibility Requirements](#python-36-compatibility-requirements)

---

## 1. Database Design & Scalability

### Phase 1: Create Database Abstraction Layer (2 weeks)

#### Tasks:
1. **Define abstract base class for database operations (no ORM)**
   ```python
   # db/interfaces/database_interface.py
   from abc import ABC, abstractmethod
   from typing import Any, Dict, List, Optional, Tuple
   
   class DatabaseInterface(ABC):
       """Direct SQL interface - no ORM"""
       @abstractmethod
       def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
           """Execute SQL with positional parameters"""
           pass
       
       @abstractmethod
       def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[Tuple]:
           """Fetch one row as tuple"""
           pass
       
       @abstractmethod
       def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[Tuple]:
           """Fetch all rows as list of tuples"""
           pass
   ```

2. **Implement SQLite adapter using stdlib only**
   ```python
   # db/adapters/sqlite_adapter.py
   import sqlite3  # stdlib only
   
   class SQLiteAdapter(DatabaseInterface):
       def __init__(self, db_path: str):
           self.db_path = db_path
       
       def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
           with sqlite3.connect(self.db_path) as conn:
               cursor = conn.cursor()
               return cursor.execute(query, params or ())
   ```

3. **Simple connection management (no external pooling libraries)**
   ```python
   # db/connection_manager.py
   import threading
   
   class SimpleConnectionManager:
       """Basic connection management using stdlib only"""
       def __init__(self, adapter_class, **kwargs):
           self.adapter_class = adapter_class
           self.config = kwargs
           self._local = threading.local()
       
       def get_connection(self):
           if not hasattr(self._local, 'adapter'):
               self._local.adapter = self.adapter_class(**self.config)
           return self._local.adapter
   ```

#### Dependencies:
- None - uses Python stdlib only

#### Testing:
- Unit tests using stdlib unittest or existing pytest
- Direct SQL testing without ORM overhead

### Phase 2: Migrate Existing Code (1 week)

#### Tasks:
1. Update `ExecutionHistoryManager` to use direct SQL
2. Update `StateManager` to use direct SQL
3. Remove any ORM-style query builders
4. Use parameterized queries for security

#### Migration Strategy:
```python
# Direct SQL approach
class ExecutionHistoryManager:
    def update_job_status(self, run_id: int, job_id: str, status: str):
        query = "UPDATE job_history SET status = ? WHERE run_id = ? AND id = ?"
        self.db.execute(query, (status, run_id, job_id))
```

### Phase 3: Add Oracle Support (1 week)

#### Tasks:
1. **Create Oracle adapter (if cx_Oracle is approved)**
   ```python
   # db/adapters/oracle_adapter.py
   # Note: Requires cx_Oracle package approval
   # Alternative: Use subprocess to call sqlplus if package not approved
   
   class OracleAdapter(DatabaseInterface):
       def __init__(self, dsn: str, user: str, password: str):
           self.connection_params = (user, password, dsn)
   ```

2. **Oracle-specific schema**
   ```sql
   -- Use NUMBER instead of INTEGER
   -- Use VARCHAR2 instead of TEXT
   -- Use TIMESTAMP instead of DATETIME
   ```

3. **Handle Oracle syntax differences**
   - Sequences instead of AUTOINCREMENT
   - DUAL table for SELECT without FROM
   - Different date formatting

---

## 2. Separation of Concerns

### Phase 1: Extract Core Components (2 weeks)

#### Tasks:
1. **Create WorkflowEngine class**
   ```python
   # core/workflow_engine.py
   class WorkflowEngine:
       def __init__(self, 
                    config_service: ConfigurationService,
                    execution_service: ExecutionService,
                    notification_service: NotificationService,
                    persistence_service: PersistenceService):
           self.config_service = config_service
           self.execution_service = execution_service
           self.notification_service = notification_service
           self.persistence_service = persistence_service
   ```

2. **Extract notification logic**
   ```python
   # services/notification_service.py
   class NotificationService:
       def __init__(self, notifiers: List[Notifier]):
           self.notifiers = notifiers
       
       def notify(self, event: ExecutionEvent):
           for notifier in self.notifiers:
               if notifier.should_notify(event):
                   notifier.send(event)
   ```

3. **Create service interfaces**
   ```python
   # services/interfaces.py
   class ExecutionService(ABC):
       @abstractmethod
       def execute_job(self, job_config: JobConfig) -> JobResult:
           pass
   ```

#### Refactoring Strategy:
1. Start with notification extraction (least coupled)
2. Extract configuration management
3. Extract execution logic
4. Finally, refactor JobExecutioner to use new services

### Phase 2: Implement Service Layer (1 week)

#### Tasks:
1. Create service factory
2. Implement service registration
3. Update dependency injection
4. Create service documentation

### Phase 3: Refactor JobExecutioner (1 week)

#### Tasks:
1. Remove extracted logic from JobExecutioner
2. Update to use new services
3. Create compatibility layer for existing code
4. Update all references

---

## 3. Error Handling & Observability

### Phase 1: Structured Error System (1 week)

#### Tasks:
1. **Define error hierarchy**
   ```python
   # core/exceptions.py
   class ExecutionerError(Exception):
       def __init__(self, message: str, error_code: str, context: Dict[str, Any] = None):
           super().__init__(message)
           self.error_code = error_code
           self.context = context or {}
           self.timestamp = datetime.utcnow()
   
   class ConfigurationError(ExecutionerError):
       pass
   
   class ExecutionError(ExecutionerError):
       pass
   
   class DependencyError(ExecutionerError):
       pass
   ```

2. **Create error handler**
   ```python
   # core/error_handler.py
   class ErrorHandler:
       def __init__(self, logger, metrics_collector):
           self.logger = logger
           self.metrics_collector = metrics_collector
       
       def handle(self, error: ExecutionerError):
           self.logger.error(
               error.message,
               extra={
                   "error_code": error.error_code,
                   "context": error.context,
                   "timestamp": error.timestamp
               }
           )
           self.metrics_collector.record_error(error)
   ```

### Phase 2: Metrics Collection (1 week)

#### Tasks:
1. **Implement metrics collector using stdlib only**
   ```python
   # monitoring/metrics.py
   import json
   import time
   import threading
   from collections import defaultdict
   from typing import Dict, Any
   
   class MetricsCollector:
       """Simple metrics collection without external dependencies"""
       def __init__(self):
           self.metrics = defaultdict(list)
           self._lock = threading.Lock()
       
       def record_job_duration(self, job_id: str, duration: float):
           with self._lock:
               self.metrics['job_duration'].append({
                   'job_id': job_id,
                   'duration': duration,
                   'timestamp': time.time()
               })
       
       def export_json(self, filepath: str):
           """Export metrics to JSON file for monitoring tools"""
           with self._lock:
               with open(filepath, 'w') as f:
                   json.dump(dict(self.metrics), f, indent=2)
   ```

2. **Create simple metrics endpoint (no Prometheus)**
   ```python
   # monitoring/metrics_server.py
   from http.server import BaseHTTPRequestHandler, HTTPServer
   import json
   
   class MetricsHandler(BaseHTTPRequestHandler):
       def do_GET(self):
           if self.path == '/metrics':
               self.send_response(200)
               self.send_header('Content-Type', 'application/json')
               self.end_headers()
               
               # Export metrics as JSON
               metrics = self.server.metrics_collector.get_current_metrics()
               self.wfile.write(json.dumps(metrics).encode())
   ```

3. **File-based metrics for integration**
   ```python
   # Write metrics to file that monitoring tools can read
   # No external dependencies required
   ```

### Phase 3: Structured Logging (1 week)

#### Tasks:
1. Implement structured logging formatter
2. Add correlation IDs for request tracking
3. Create log aggregation configuration
4. Add log sampling for high-volume events

---

## 4. Testing & Dependency Injection

### Phase 1: Dependency Injection Framework (1 week)

#### Tasks:
1. **Create DI container**
   ```python
   # core/container.py
   class Container:
       def __init__(self):
           self._services = {}
           self._singletons = {}
           self._factories = {}
       
       def register(self, interface: Type, implementation: Type, lifetime: str = 'transient'):
           if lifetime == 'singleton':
               self._singletons[interface] = None
           self._services[interface] = (implementation, lifetime)
       
       def resolve(self, interface: Type) -> Any:
           if interface in self._singletons and self._singletons[interface]:
               return self._singletons[interface]
           
           implementation, lifetime = self._services[interface]
           instance = self._create_instance(implementation)
           
           if lifetime == 'singleton':
               self._singletons[interface] = instance
           
           return instance
   ```

2. **Create service registration**
   ```python
   # core/bootstrap.py
   def configure_services(container: Container):
       container.register(DatabaseInterface, SQLiteAdapter, 'singleton')
       container.register(ProcessExecutor, SubprocessExecutor, 'transient')
       container.register(NotificationService, EmailNotificationService, 'singleton')
   ```

### Phase 2: Abstract External Dependencies (1 week)

#### Tasks:
1. **Abstract process execution**
   ```python
   # core/interfaces/process_executor.py
   class ProcessExecutor(ABC):
       @abstractmethod
       async def execute(self, 
                        command: str, 
                        env: Dict[str, str], 
                        timeout: Optional[int]) -> ProcessResult:
           pass
   ```

2. **Abstract file system operations**
   ```python
   # core/interfaces/file_system.py
   class FileSystem(ABC):
       @abstractmethod
       def read_file(self, path: str) -> str:
           pass
       
       @abstractmethod
       def write_file(self, path: str, content: str):
           pass
   ```

3. **Create mock implementations**

### Phase 3: Test Infrastructure (1 week)

#### Tasks:
1. Create test fixtures and factories
2. Implement test database with transactions
3. Add integration test framework
4. Create performance test suite

---

## 5. Async/Await Implementation

### Phase 1: Async Job Runner (2 weeks)

#### Tasks:
1. **Create async job runner**
   ```python
   # jobs/async_job_runner.py
   class AsyncJobRunner:
       def __init__(self, process_executor: ProcessExecutor, max_concurrent: int = 10):
           self.process_executor = process_executor
           self.semaphore = asyncio.Semaphore(max_concurrent)
       
       async def run(self, job_config: JobConfig) -> JobResult:
           async with self.semaphore:
               start_time = time.time()
               try:
                   result = await self.process_executor.execute(
                       job_config.command,
                       job_config.env_variables,
                       job_config.timeout
                   )
                   return JobResult(
                       job_id=job_config.id,
                       status=JobState.SUCCESS if result.exit_code == 0 else JobState.FAILED,
                       exit_code=result.exit_code,
                       stdout=result.stdout,
                       stderr=result.stderr,
                       duration=time.time() - start_time
                   )
               except asyncio.TimeoutError:
                   return JobResult(
                       job_id=job_config.id,
                       status=JobState.TIMEOUT,
                       duration=time.time() - start_time
                   )
   ```

2. **Implement async orchestrator**
   ```python
   # orchestration/async_orchestrator.py
   class AsyncOrchestrator:
       async def run_workflow(self, workflow: Workflow) -> WorkflowResult:
           pending_jobs = set(workflow.jobs)
           completed_jobs = set()
           
           async with asyncio.TaskGroup() as tg:
               while pending_jobs:
                   ready_jobs = self.get_ready_jobs(pending_jobs, completed_jobs)
                   for job in ready_jobs:
                       tg.create_task(self.run_job(job))
                   
                   # Wait for at least one job to complete
                   await self.job_completed.wait()
   ```

### Phase 2: Async Database Operations (1 week)

#### Tasks:
1. Add async database interface
2. Implement async SQLite with aiosqlite
3. Update persistence layer for async
4. Add connection pooling for async

### Phase 3: Migration Strategy (1 week)

#### Tasks:
1. Create sync/async adapter layer
2. Gradually migrate endpoints to async
3. Update CLI to use asyncio.run()
4. Performance testing and optimization

---

## 6. Configuration Management

### Phase 1: Configuration Models using stdlib (1 week)

#### Tasks:
1. **Define configuration models using dataclasses (stdlib in 3.7+)**
   ```python
   # config/models.py
   # Use dataclasses with custom validation - no external packages
   import sys
   from typing import List, Dict, Optional
   from pathlib import Path
   
   # Python 3.6 compatibility
   if sys.version_info >= (3, 7):
       from dataclasses import dataclass, field
   else:
       from dataclasses import dataclass, field  # backport - minimal package
   
   @dataclass
   class JobConfig:
       id: str
       command: str
       timeout: int = 3600
       dependencies: List[str] = field(default_factory=list)
       env_variables: Dict[str, str] = field(default_factory=dict)
       
       def validate(self) -> List[str]:
           """Custom validation without external packages"""
           errors = []
           if not self.id:
               errors.append("Job ID cannot be empty")
           if not self.command:
               errors.append("Command cannot be empty")
           if self.timeout <= 0:
               errors.append("Timeout must be positive")
           if len(self.dependencies) != len(set(self.dependencies)):
               errors.append("Duplicate dependencies found")
           return errors
   
   @dataclass
   class WorkflowConfig:
       application_name: str
       working_dir: str
       jobs: List[JobConfig]
       
       def validate(self) -> List[str]:
           """Validate entire workflow configuration"""
           errors = []
           if not self.application_name:
               errors.append("Application name required")
           
           # Check working directory
           wd = Path(self.working_dir)
           if not wd.exists():
               errors.append(f"Working directory {self.working_dir} does not exist")
           
           # Validate all jobs
           job_ids = set()
           for job in self.jobs:
               job_errors = job.validate()
               errors.extend([f"Job {job.id}: {e}" for e in job_errors])
               
               if job.id in job_ids:
                   errors.append(f"Duplicate job ID: {job.id}")
               job_ids.add(job.id)
           
           return errors
   ```

2. **Create configuration parser (stdlib json)**
   ```python
   # config/parser.py
   import json
   from typing import Dict, Any
   
   def parse_config(filepath: str) -> WorkflowConfig:
       """Parse JSON config using stdlib only"""
       with open(filepath, 'r') as f:
           data = json.load(f)
       
       # Convert dict to dataclass
       jobs = [JobConfig(**job_data) for job_data in data.get('jobs', [])]
       config = WorkflowConfig(
           application_name=data['application_name'],
           working_dir=data['working_dir'],
           jobs=jobs
       )
       
       # Validate
       errors = config.validate()
       if errors:
           raise ValueError(f"Configuration errors: {'; '.join(errors)}")
       
       return config
   ```

3. **Add configuration builder helpers**

### Phase 2: Configuration Templates (1 week)

#### Tasks:
1. **Implement template system**
   ```python
   # config/templates.py
   class ConfigTemplateEngine:
       def __init__(self):
           self.templates = {}
       
       def register_template(self, name: str, template: Dict[str, Any]):
           self.templates[name] = template
       
       def apply_template(self, config: Dict[str, Any], template_name: str) -> Dict[str, Any]:
           template = self.templates[template_name]
           return deep_merge(template, config)
   ```

2. **Add include functionality**
   ```python
   # config/loader.py
   class ConfigLoader:
       def load_with_includes(self, config_path: Path) -> WorkflowConfig:
           config_data = self.load_file(config_path)
           
           if 'includes' in config_data:
               for include_path in config_data['includes']:
                   included_config = self.load_file(include_path)
                   config_data = self.merge_configs(config_data, included_config)
           
           return WorkflowConfig(**config_data)
   ```

### Phase 3: Configuration Validation Service (1 week)

#### Tasks:
1. Create validation rules engine
2. Add custom validators
3. Implement configuration linting
4. Create configuration migration tools

---

## 7. State Management

### Phase 1: State Machine Implementation (1 week)

#### Tasks:
1. **Define state machine**
   ```python
   # state/state_machine.py
   from enum import Enum, auto
   from typing import Dict, Set, Optional
   
   class JobState(Enum):
       PENDING = auto()
       QUEUED = auto()
       RUNNING = auto()
       SUCCESS = auto()
       FAILED = auto()
       TIMEOUT = auto()
       SKIPPED = auto()
       CANCELLED = auto()
   
   class JobStateMachine:
       TRANSITIONS: Dict[JobState, Set[JobState]] = {
           JobState.PENDING: {JobState.QUEUED, JobState.SKIPPED, JobState.CANCELLED},
           JobState.QUEUED: {JobState.RUNNING, JobState.SKIPPED, JobState.CANCELLED},
           JobState.RUNNING: {JobState.SUCCESS, JobState.FAILED, JobState.TIMEOUT, JobState.CANCELLED},
           JobState.SUCCESS: set(),
           JobState.FAILED: {JobState.QUEUED},  # For retry
           JobState.TIMEOUT: {JobState.QUEUED},  # For retry
           JobState.SKIPPED: set(),
           JobState.CANCELLED: set()
       }
       
       def can_transition(self, from_state: JobState, to_state: JobState) -> bool:
           return to_state in self.TRANSITIONS.get(from_state, set())
       
       def transition(self, job_id: str, from_state: JobState, to_state: JobState) -> bool:
           if not self.can_transition(from_state, to_state):
               raise InvalidStateTransition(
                   f"Cannot transition job {job_id} from {from_state} to {to_state}"
               )
           return True
   ```

2. **Create state persistence**
   ```python
   # state/state_store.py
   class StateStore:
       def __init__(self, db_interface: DatabaseInterface):
           self.db = db_interface
           self.state_machine = JobStateMachine()
       
       async def update_job_state(self, job_id: str, new_state: JobState) -> None:
           current_state = await self.get_job_state(job_id)
           self.state_machine.transition(job_id, current_state, new_state)
           
           await self.db.execute(
               "UPDATE job_history SET status = ?, updated_at = ? WHERE job_id = ?",
               {"status": new_state.name, "updated_at": datetime.utcnow(), "job_id": job_id}
           )
   ```

### Phase 2: Event-Driven State Updates (1 week)

#### Tasks:
1. Implement event bus
2. Create state change events
3. Add event handlers
4. Implement audit logging

### Phase 3: State Visualization (1 week)

#### Tasks:
1. Create state diagram generator
2. Add real-time state monitoring
3. Implement state history tracking
4. Add state analytics

---

## 8. API-First Design

### Phase 1: Core API Implementation (2 weeks)

#### Tasks:
1. **Define API interfaces**
   ```python
   # api/interfaces.py
   from typing import Optional, List
   from datetime import datetime
   
   class ExecutionerAPI(ABC):
       @abstractmethod
       async def submit_workflow(self, config: WorkflowConfig) -> str:
           """Submit a workflow and return run_id"""
           pass
       
       @abstractmethod
       async def get_run_status(self, run_id: str) -> RunStatus:
           """Get current status of a run"""
           pass
       
       @abstractmethod
       async def get_job_status(self, run_id: str, job_id: str) -> JobStatus:
           """Get status of a specific job"""
           pass
       
       @abstractmethod
       async def cancel_run(self, run_id: str) -> bool:
           """Cancel a running workflow"""
           pass
       
       @abstractmethod
       async def list_runs(self, 
                          application_name: Optional[str] = None,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None,
                          limit: int = 100) -> List[RunSummary]:
           """List workflow runs with filtering"""
           pass
   ```

2. **Implement API service**
   ```python
   # api/service.py
   class ExecutionerAPIService(ExecutionerAPI):
       def __init__(self, 
                    workflow_engine: WorkflowEngine,
                    state_store: StateStore,
                    persistence: PersistenceService):
           self.workflow_engine = workflow_engine
           self.state_store = state_store
           self.persistence = persistence
       
       async def submit_workflow(self, config: WorkflowConfig) -> str:
           # Validate configuration
           validation_result = await self.validate_config(config)
           if not validation_result.is_valid:
               raise ValidationError(validation_result.errors)
           
           # Generate run ID
           run_id = self.generate_run_id()
           
           # Submit to workflow engine
           await self.workflow_engine.submit(run_id, config)
           
           return run_id
   ```

### Phase 2: REST API Layer using stdlib (1 week)

#### Tasks:
1. **Implement HTTP API using stdlib http.server**
   ```python
   # api/rest/server.py
   from http.server import BaseHTTPRequestHandler, HTTPServer
   import json
   import urllib.parse
   from typing import Dict, Any
   
   class ExecutionerAPIHandler(BaseHTTPRequestHandler):
       """Simple REST API using stdlib only - no external frameworks"""
       
       def do_POST(self):
           """Handle POST requests"""
           if self.path == '/workflows':
               # Submit new workflow
               content_length = int(self.headers['Content-Length'])
               post_data = self.rfile.read(content_length)
               
               try:
                   config_data = json.loads(post_data)
                   run_id = self.server.api_service.submit_workflow(config_data)
                   
                   response = {'run_id': run_id, 'status': 'submitted'}
                   self._send_json_response(200, response)
               except json.JSONDecodeError:
                   self._send_json_response(400, {'error': 'Invalid JSON'})
               except ValueError as e:
                   self._send_json_response(400, {'error': str(e)})
       
       def do_GET(self):
           """Handle GET requests"""
           parsed = urllib.parse.urlparse(self.path)
           
           if parsed.path.startswith('/runs/'):
               # Get run status
               run_id = parsed.path.split('/')[-1]
               status = self.server.api_service.get_run_status(run_id)
               
               if status:
                   self._send_json_response(200, status)
               else:
                   self._send_json_response(404, {'error': 'Run not found'})
           else:
               self._send_json_response(404, {'error': 'Not found'})
       
       def _send_json_response(self, code: int, data: Dict[str, Any]):
           """Helper to send JSON responses"""
           self.send_response(code)
           self.send_header('Content-Type', 'application/json')
           self.end_headers()
           self.wfile.write(json.dumps(data).encode())
   
   # Start server
   def run_api_server(api_service, port=8080):
       server = HTTPServer(('', port), ExecutionerAPIHandler)
       server.api_service = api_service
       server.serve_forever()
   ```

2. **Add basic authentication (stdlib only)**
   ```python
   # Simple Basic Auth using stdlib
   import base64
   
   def check_auth(self, auth_header):
       if not auth_header or not auth_header.startswith('Basic '):
           return False
       
       encoded = auth_header[6:]
       decoded = base64.b64decode(encoded).decode('utf-8')
       username, password = decoded.split(':', 1)
       
       # Check against configured users
       return self.server.check_credentials(username, password)
   ```

3. **Simple rate limiting using stdlib**
4. **Manual API documentation (no OpenAPI)**

### Phase 3: CLI Refactoring (1 week)

#### Tasks:
1. Refactor CLI to use API
2. Add API client library
3. Maintain backward compatibility
4. Update documentation

---

## 9. Resource Management

### Phase 1: Resource Tracking (1 week)

#### Tasks:
1. **Implement resource manager**
   ```python
   # resources/manager.py
   import psutil
   from dataclasses import dataclass
   from typing import Optional
   
   @dataclass
   class ResourceRequirements:
       cpu_cores: Optional[float] = None
       memory_mb: Optional[int] = None
       disk_mb: Optional[int] = None
   
   class ResourceManager:
       def __init__(self, 
                    max_cpu_percent: float = 80.0,
                    max_memory_percent: float = 80.0):
           self.max_cpu_percent = max_cpu_percent
           self.max_memory_percent = max_memory_percent
           self.allocated_resources = {}
       
       def can_allocate(self, job_id: str, requirements: ResourceRequirements) -> bool:
           current_usage = self.get_current_usage()
           
           # Check CPU
           if requirements.cpu_cores:
               cpu_percent = (requirements.cpu_cores / psutil.cpu_count()) * 100
               if current_usage.cpu_percent + cpu_percent > self.max_cpu_percent:
                   return False
           
           # Check memory
           if requirements.memory_mb:
               total_memory = psutil.virtual_memory().total / (1024 * 1024)
               memory_percent = (requirements.memory_mb / total_memory) * 100
               if current_usage.memory_percent + memory_percent > self.max_memory_percent:
                   return False
           
           return True
       
       def allocate(self, job_id: str, requirements: ResourceRequirements):
           if not self.can_allocate(job_id, requirements):
               raise ResourceExhausted("Insufficient resources")
           self.allocated_resources[job_id] = requirements
       
       def release(self, job_id: str):
           self.allocated_resources.pop(job_id, None)
   ```

2. **Add resource monitoring**
3. **Implement resource limits**

### Phase 2: Job Prioritization (1 week)

#### Tasks:
1. **Implement priority queue**
   ```python
   # scheduling/priority_queue.py
   import heapq
   from dataclasses import dataclass, field
   from typing import Any
   
   @dataclass(order=True)
   class PrioritizedJob:
       priority: int
       timestamp: float = field(compare=False)
       job: Any = field(compare=False)
   
   class PriorityJobQueue:
       def __init__(self):
           self._queue = []
           self._job_finder = {}
       
       def push(self, job: JobConfig, priority: int = 0):
           if job.id in self._job_finder:
               self.remove(job.id)
           
           entry = PrioritizedJob(
               priority=-priority,  # Negative for max heap
               timestamp=time.time(),
               job=job
           )
           
           self._job_finder[job.id] = entry
           heapq.heappush(self._queue, entry)
       
       def pop(self) -> Optional[JobConfig]:
           while self._queue:
               entry = heapq.heappop(self._queue)
               if entry.job.id in self._job_finder:
                   del self._job_finder[entry.job.id]
                   return entry.job
           return None
   ```

2. **Add priority rules engine**
3. **Implement fair scheduling**

### Phase 3: Resource Policies (1 week)

#### Tasks:
1. Create resource policy framework
2. Implement quota management
3. Add resource reservation
4. Create resource usage reports

---

## 10. Modern Python Features (Python 3.6+ Compatible)

### Phase 1: Type Hints Throughout (1 week)

#### Tasks:
1. **Add comprehensive type hints (Python 3.6 compatible)**
   ```python
   # Example of fully typed function with Python 3.6 compatibility
   from typing import Dict, List, Optional, Union, Tuple, Any
   # For Python 3.6, use typing_extensions for advanced types
   try:
       from typing import Protocol, TypedDict, Literal  # Python 3.8+
   except ImportError:
       from typing_extensions import Protocol, TypedDict, Literal
   
   def process_job_config(
       config_path: str,  # Use str instead of Path for type hints in 3.6
       overrides: Optional[Dict[str, Any]] = None,
       validate: bool = True
   ) -> Tuple['JobConfig', List['ValidationError']]:
       """
       Process job configuration with optional overrides.
       
       Args:
           config_path: Path to configuration file
           overrides: Optional configuration overrides
           validate: Whether to validate configuration
           
       Returns:
           Tuple of JobConfig and list of validation errors
       """
       from pathlib import Path  # Import Path for usage, not type hints
       
       errors: List[ValidationError] = []
       config_data = load_config(Path(config_path))
       
       if overrides:
           config_data = merge_configs(config_data, overrides)
       
       if validate:
           errors = validate_config(config_data)
       
       return JobConfig(**config_data), errors
   ```

2. **Add mypy configuration for Python 3.6**
   ```ini
   # mypy.ini
   [mypy]
   python_version = 3.6  # Set to minimum supported version
   warn_return_any = True
   warn_unused_configs = True
   disallow_untyped_defs = True
   disallow_incomplete_defs = True
   check_untyped_defs = True
   disallow_untyped_decorators = True
   no_implicit_optional = True
   warn_redundant_casts = True
   warn_unused_ignores = True
   warn_no_return = True
   warn_unreachable = True
   strict_equality = True
   
   # Allow typing_extensions
   [mypy-typing_extensions]
   ignore_missing_imports = True
   ```

### Phase 2: Dataclasses and Modern Patterns (1 week)

#### Tasks:
1. **Convert to dataclasses (Python 3.6 compatible)**
   ```python
   # models/job_models.py
   import sys
   
   # Handle dataclasses import for Python 3.6
   if sys.version_info >= (3, 7):
       from dataclasses import dataclass, field
   else:
       # Use backport for Python 3.6
       from dataclasses import dataclass, field  # pip install dataclasses
   
   from datetime import datetime
   from typing import Optional, Dict, Any
   
   @dataclass
   class JobResult:
       job_id: str
       status: str  # Use string instead of Enum for simpler 3.6 compatibility
       start_time: datetime
       end_time: datetime
       exit_code: Optional[int] = None
       stdout: str = ""
       stderr: str = ""
       error_message: Optional[str] = None
       retry_count: int = 0
       metadata: Dict[str, Any] = field(default_factory=dict)
       
       @property
       def duration(self) -> float:
           return (self.end_time - self.start_time).total_seconds()
       
       @property
       def is_success(self) -> bool:
           return self.status == "SUCCESS"
   ```

2. **Use traditional conditionals instead of pattern matching**
   ```python
   # Python 3.6 compatible (no pattern matching)
   def handle_job_result(result: JobResult) -> None:
       if result.status == "SUCCESS":
           logger.info(f"Job {result.job_id} completed successfully")
       elif result.status in ("FAILED", "TIMEOUT"):
           logger.error(f"Job {result.job_id} failed: {result.error_message}")
           if result.retry_count < max_retries:
               schedule_retry(result.job_id)
       elif result.status == "SKIPPED":
           logger.warning(f"Job {result.job_id} was skipped")
       else:
               logger.error(f"Unknown job status: {result.status}")
   ```

### Phase 3: Performance Optimizations (1 week)

#### Tasks:
1. Profile existing code
2. Optimize hot paths
3. Add caching where appropriate
4. Use slots for frequently created objects

---

## Implementation Timeline

### Quarter 1 (Months 1-3)

**Month 1:**
- Week 1-2: Database Abstraction Layer
- Week 3-4: Testing & Dependency Injection Framework

**Month 2:**
- Week 1-2: Error Handling & Observability
- Week 3-4: Configuration Management

**Month 3:**
- Week 1-2: State Management
- Week 3-4: Modern Python Features

### Quarter 2 (Months 4-6)

**Month 4:**
- Week 1-2: Separation of Concerns
- Week 3-4: Start Async/Await Implementation

**Month 5:**
- Week 1-2: Complete Async/Await Implementation
- Week 3-4: API-First Design (Core API)

**Month 6:**
- Week 1-2: API-First Design (REST API)
- Week 3-4: Resource Management

### Implementation Priorities

1. **High Priority (Do First):**
   - Database Abstraction (foundation for other changes)
   - Error Handling & Observability (immediate benefits)
   - Testing & Dependency Injection (enables safe refactoring)

2. **Medium Priority:**
   - State Management (improves reliability)
   - Configuration Management (better user experience)
   - Modern Python Features (code quality)

3. **Lower Priority (Can be deferred):**
   - Full Async implementation (performance optimization)
   - Resource Management (advanced feature)
   - Complete API layer (nice to have)

### Risk Mitigation

1. **Backward Compatibility:**
   - Maintain existing CLI interface
   - Provide migration tools
   - Use feature flags for gradual rollout

2. **Testing Strategy:**
   - Comprehensive test suite before major refactoring
   - Integration tests for each phase
   - Performance benchmarks

3. **Rollback Plan:**
   - Version all changes
   - Maintain stable branch
   - Document rollback procedures

### Success Metrics

1. **Code Quality:**
   - 90%+ test coverage
   - Zero mypy errors
   - Reduced cyclomatic complexity

2. **Performance:**
   - 50% reduction in job startup time
   - 3x improvement in parallel execution throughput
   - 80% reduction in database query time

3. **Reliability:**
   - 99.9% successful job execution rate
   - Zero data loss during failures
   - Successful recovery from all failure modes

4. **Developer Experience:**
   - 50% reduction in time to add new features
   - Clear documentation for all components
   - Easy debugging with structured logging

---

## Conclusion

This implementation plan provides a structured approach to modernizing the Executioner architecture. Each phase builds upon previous work, allowing for incremental improvements while maintaining system stability. The plan prioritizes changes that provide immediate value while laying the groundwork for more advanced features.

Key success factors:
- Incremental implementation with continuous delivery
- Comprehensive testing at each phase
- Clear communication with users about changes
- Maintaining backward compatibility where possible
- Regular performance and quality metrics tracking

The total implementation timeline is approximately 6 months for the complete modernization, but benefits will be realized incrementally throughout the process.

---

## Python 3.6 Compatibility Requirements

### Overview

All code implementations MUST maintain compatibility with Python 3.6 as the minimum supported version. This section outlines the specific requirements and guidelines for ensuring compatibility.

### Required Dependencies

Add to `requirements.txt` or `setup.py`:
```txt
# Python 3.6 compatibility packages
dataclasses>=0.6; python_version < '3.7'
typing_extensions>=3.7.4; python_version < '3.8'
contextvars>=2.4; python_version < '3.7'  # For async context
```

### Compatibility Patterns

#### 1. Import Handling
```python
# Always use conditional imports for version-specific features
import sys

if sys.version_info >= (3, 7):
    from dataclasses import dataclass, field
else:
    from dataclasses import dataclass, field  # backport

# For typing extensions
try:
    from typing import Protocol, TypedDict, Literal  # Python 3.8+
except ImportError:
    from typing_extensions import Protocol, TypedDict, Literal
```

#### 2. Feature Compatibility Table

| Feature | Python 3.6 | Alternative |
|---------|------------|-------------|
| f-strings | ✅ Supported | Use freely |
| Type hints | ✅ Basic support | Use typing_extensions for advanced types |
| Dataclasses | ❌ Not supported | Use dataclasses backport |
| Walrus operator `:=` | ❌ Not supported | Use traditional assignment |
| Dict merge `\|` | ❌ Not supported | Use `{**dict1, **dict2}` |
| Positional-only `/` | ❌ Not supported | Document in docstrings |
| Pattern matching | ❌ Not supported | Use if/elif chains |
| `asyncio.run()` | ❌ Not supported | Use event loop directly |

#### 3. Testing Requirements

1. **CI/CD Configuration**:
   ```yaml
   # .github/workflows/test.yml or similar
   python-version: [3.6, 3.7, 3.8, 3.9, 3.10, 3.11]
   ```

2. **Local Testing**:
   ```bash
   # Test with Python 3.6 before committing
   pyenv local 3.6.15  # or latest 3.6.x
   python -m pytest
   mypy --python-version 3.6 .
   ```

#### 4. Code Review Checklist

Before committing any code:
- [ ] No walrus operators (`:=`)
- [ ] No native dataclasses without import guards
- [ ] No pattern matching (`match`/`case`)
- [ ] No positional-only parameters (`/`)
- [ ] No dict merge operators (`|`)
- [ ] All type hints use `typing_extensions` when needed
- [ ] Tested on Python 3.6
- [ ] Mypy passes with `python_version = 3.6`

#### 5. Common Pitfalls to Avoid

1. **String annotations** (Python 3.7+):
   ```python
   # Don't use
   def func() -> 'SomeClass':  # Might fail in 3.6
   
   # Do use
   from __future__ import annotations  # At top of file
   ```

2. **Dict ordering** (guaranteed in 3.7+):
   ```python
   # Don't rely on dict ordering in 3.6
   # Use OrderedDict if order matters
   from collections import OrderedDict
   ```

3. **Async comprehensions** (Python 3.6 has limited support):
   ```python
   # Be careful with async comprehensions
   # Test thoroughly on Python 3.6
   ```

### Version Constants

Add to a central location (e.g., `core/compat.py`):
```python
import sys

PY36 = sys.version_info[:2] == (3, 6)
PY37_PLUS = sys.version_info >= (3, 7)
PY38_PLUS = sys.version_info >= (3, 8)
PY39_PLUS = sys.version_info >= (3, 9)
PY310_PLUS = sys.version_info >= (3, 10)

# Use these for conditional logic
if PY37_PLUS:
    # Use newer features
else:
    # Use compatibility code
```

### Documentation

Always document Python version requirements:
- In README.md: "Requires Python 3.6 or higher"
- In setup.py: `python_requires='>=3.6'`
- In function docstrings when using version-specific features

By following these guidelines, we ensure that the Executioner remains accessible to users who may be constrained to Python 3.6 environments while still leveraging modern Python features where available.