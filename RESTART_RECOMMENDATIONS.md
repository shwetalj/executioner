# Executioner Restart Logic Analysis & Recommendations

**Analysis Date:** 2026-01-08
**Version:** Based on current main branch

---

## Executive Summary

This document provides a comprehensive analysis of the restart logic in the Executioner workflow orchestration system. The analysis covers:
- Job restart mechanisms after failure
- Midstream workflow execution capabilities
- Run ID and attempt management
- Execution history tracking
- Dependency handling during restarts
- Edge cases and potential issues

**Overall Assessment:** The core restart mechanism using `run_id` and `attempt_id` is well-designed, but several critical gaps exist in midstream restarts, config validation, and audit trail management.

---

## Table of Contents

1. [What Works Well](#what-works-well)
2. [Critical Issues Found](#critical-issues-found)
3. [Edge Cases & Scenarios](#edge-cases--scenarios)
4. [Detailed Technical Analysis](#detailed-technical-analysis)
5. [Recommendations](#recommendations)
6. [Test Scenarios](#test-scenarios)

---

## What Works Well

### 1. Run ID & Attempt Management

**Location:** `execution_history_manager.py:20-44`, `state_manager.py:64-86`

**Design:**
- **Same run_id is reused across restart attempts** - Excellent for tracking related executions
- Attempt counter increments for each resume
- Database schema supports composite key: `(run_id, attempt_id, job_id)`

**Example:**
```
Fresh run:    run_id=5, attempt_id=1
First resume: run_id=5, attempt_id=2
Next resume:  run_id=5, attempt_id=3
```

**Database Schema:**
```sql
-- run_summary table
PRIMARY KEY (run_id, attempt_id)

-- job_history table
PRIMARY KEY (run_id, attempt_id, id)
```

### 2. Built-in Job Retry Logic

**Location:** `jobs/job_runner.py:96-200`

**Features:**
- Configurable retry parameters: `max_retries`, `retry_delay`, `retry_backoff`, `retry_jitter`
- Exponential backoff: `base_delay * (retry_backoff ^ attempt)`
- Jitter randomization prevents thundering herd
- Configurable retry conditions:
  - `retry_on_status`: List of statuses triggering retry (ERROR, FAILED, TIMEOUT)
  - `retry_on_exit_codes`: Specific exit codes triggering retry
- Maximum retry time enforcement: `max_retry_time`
- Retry history logged as JSON

**Example Configuration:**
```json
{
  "id": "flaky_job",
  "max_retries": 3,
  "retry_delay": 5,
  "retry_backoff": 2,
  "retry_jitter": 2,
  "retry_on_status": ["ERROR", "FAILED"],
  "retry_on_exit_codes": [1, 2, 255]
}
```

### 3. Resume Mechanisms

**Location:** `executioner.py:719-733`, `state_manager.py:157-228`

**Two Resume Modes:**

1. **Normal Resume** (`--resume-from <RUN_ID>`):
   - Skips successfully completed jobs
   - Re-runs failed/error/timeout jobs
   - Re-runs pending jobs

2. **Failed-Only Resume** (`--resume-failed-only`):
   - Only re-runs jobs with FAILED/ERROR/TIMEOUT status
   - Skips successful AND pending jobs

**Usage:**
```bash
# Resume entire workflow, skip successful jobs
executioner.py -c config.json --resume-from 123

# Resume only failed jobs
executioner.py -c config.json --resume-from 123 --resume-failed-only
```

### 4. Dependency Resolution

**Location:** `queue_manager.py:136-213`

**Logic:**
- Jobs queue only when ALL dependencies are satisfied
- Dependencies satisfied if job is in: `completed_jobs` OR `skip_jobs`
- Failed dependencies prevent downstream job execution
- Supports both serial and parallel execution modes

---

## Critical Issues Found

### Issue #1: NO Native Midstream Restart Support

**Severity:** HIGH
**Location:** N/A (feature doesn't exist)

**Question:** "If a workflow had to be started midstream, how would that work?"

**Answer:** It doesn't work natively! Currently requires manual workaround:

**Current Workaround:**
```bash
# Step 1: Manually mark preceding jobs as successful
executioner.py --mark-success -r 123 -j job1,job2,job3

# Step 2: Resume the run
executioner.py --resume-from 123
```

**Problems:**
1. **Error-prone manual process** - Easy to mark wrong jobs
2. **No dependency validation** - System doesn't verify dependencies are satisfied
3. **No safety checks** - Could mark jobs successful that never ran
4. **Poor user experience** - Requires multiple commands and knowledge of job IDs

**Example Failure Scenario:**
```
Workflow: job1 → job2 → job3 → job4

Goal: Start from job3

User mistakenly marks: job1 (forgets job2)
Result: job3 runs without job2's output → FAILS
```

**Recommended Solution:**
Add `--from-job <JOB_ID>` flag that:
- Automatically identifies all preceding jobs
- Validates their dependencies
- Marks them as successful
- Queues the target job and all downstream jobs

---

### Issue #2: Config Changes Not Validated on Resume

**Severity:** CRITICAL
**Location:** `state_manager.py:157-198`

**Problem:** When resuming, the system WARNS but DOESN'T STOP if job definitions have changed between attempts.

**Dangerous Scenario:**
```
# Attempt 1
Job config: {"id": "extract", "command": "fetch_from_api_v1"}
Run fails after extract succeeds

# User changes config
Job config: {"id": "extract", "command": "fetch_from_api_v2"}

# Resume attempt 1
executioner.py --resume-from 123

PROBLEM: Which command actually ran?
- Database has status from v1
- Config shows v2
- No tracking of which version executed
- Downstream jobs may expect v2 data but got v1
```

**Current Behavior:**
```python
# state_manager.py:178-186
if len(previous_jobs) != len(config_jobs):
    logger.warning(
        f"Job count mismatch: config has {len(config_jobs)}, "
        f"previous run had {len(previous_jobs)}"
    )
    # CONTINUES ANYWAY!
```

**Impact:**
- **Silent data corruption** - Wrong version of data used
- **Inconsistent state** - Database shows old execution
- **Debugging nightmare** - Can't tell which version ran
- **Audit failure** - No compliance trail

**Recommended Solution:**
1. **Strict mode (default):** Fail resume if ANY job definition changed
2. **Permissive mode (flag):** Allow resume but log changes to audit table
3. **Hash tracking:** Store config hash per attempt to detect changes

---

### Issue #3: "Ghost Attempts" Created

**Severity:** MEDIUM
**Location:** `state_manager.py:74-85`

**Problem:** Attempt ID increments even if run fails immediately before executing any jobs.

**Scenario:**
```
Attempt 1: Runs, some jobs fail
Resume command: executioner.py --resume-from 123
  → attempt_id=2 created in run_summary
  → Run fails due to config validation error
  → NO jobs execute
  → attempt_id=2 exists in DB with no job records

Next resume: executioner.py --resume-from 123
  → attempt_id=3 created
  → Attempt 2 is a "ghost" with no data
```

**Current Code:**
```python
def initialize_run(self, resume_run_id=None):
    if resume_run_id:
        self.run_id = resume_run_id
        self.attempt_id = get_next_attempt_id(resume_run_id)  # Increments HERE
    else:
        self.run_id = get_new_run_id()
        self.attempt_id = 1

    # Run summary created immediately
    create_run_summary(self.run_id, self.attempt_id, ...)

    # If error occurs before jobs execute, attempt is "ghost"
```

**Impact:**
- Database pollution with empty attempt records
- Confusing audit trail
- Attempt numbering has gaps
- Queries must filter out ghost attempts

**Recommended Solution:**
Only create run_summary when first job starts executing, not during initialization.

---

### Issue #4: Retry History Only Captures Failures

**Severity:** MEDIUM
**Location:** `jobs/job_runner.py:209-223`

**Problem:** Retry history is only recorded in the finally block AFTER all retries are exhausted.

**Current Behavior:**
```python
try:
    for attempt in range(max_retries + 1):
        result = execute_job()
        if result.success:
            return result  # EXITS - No history recorded!
        retry_history.append({...})
finally:
    # Only reaches here if all retries failed
    update_job_status(retry_history=retry_history)
```

**Example:**
```
Job executes:
- Attempt 1: FAILED (exit code 1)
- Attempt 2: FAILED (exit code 2)
- Attempt 3: SUCCESS (exit code 0)

Database shows:
- status: SUCCESS
- retry_count: 2
- retry_history: NULL  ← Lost the failure history!
```

**Impact:**
- **Lost audit trail** - Can't see which attempts failed
- **Debugging difficulty** - Can't analyze retry patterns
- **Monitoring gaps** - Can't track job reliability
- **Compliance issues** - No record of transient failures

**Recommended Solution:**
Record retry history even on success, showing all attempts including the final successful one.

---

### Issue #5: Exit Codes Not Preserved

**Severity:** HIGH
**Location:** `execution_history_manager.py:765-794`

**Problem:** The `last_exit_code` column exists in the database schema but is **NEVER populated** during job execution.

**Current Code:**
```python
def get_last_exit_code(run_id, job_id):
    """Get last exit code for a job"""
    cursor.execute(
        "SELECT last_exit_code FROM job_history WHERE run_id=? AND id=?",
        (run_id, job_id)
    )
    result = cursor.fetchone()
    return result[0] if result else None
    # ALWAYS RETURNS NULL!
```

**Missing Code:**
```python
# job_runner.py - This should exist but doesn't:
update_job_status(
    job_id=job.id,
    status=result.status,
    exit_code=result.exit_code,  # ← Never passed!
    ...
)
```

**Impact:**
1. **Retry logic broken** - Can't use `retry_on_exit_codes` on resume
2. **Debugging difficulty** - Can't determine why job failed
3. **Monitoring gaps** - Can't alert on specific exit codes
4. **Lost information** - Exit code only in logs, not queryable

**Example Failure:**
```json
{
  "id": "backup_job",
  "retry_on_exit_codes": [1, 2],  // Only retry on specific codes
  "max_retries": 3
}
```

On resume:
- `get_last_exit_code()` returns NULL
- System can't determine if exit code qualifies for retry
- Falls back to status-based retry (less precise)

**Recommended Solution:**
1. Update `update_job_status()` to accept `exit_code` parameter
2. Populate `last_exit_code` column during execution
3. Update resume logic to check exit codes

---

### Issue #6: No Rollback Support

**Severity:** MEDIUM
**Location:** `execution_history_manager.py:649-669`

**Problem:** Job statuses are committed to database immediately upon completion, even if later jobs fail. No transaction rollback capability.

**Current Behavior:**
```python
def commit_job_statuses(self):
    """Commit all pending job statuses"""
    cursor.executemany(
        "INSERT INTO job_history ... ON CONFLICT DO UPDATE ...",
        pending_updates
    )
    conn.commit()  # ← Immediate commit, no rollback
```

**Scenario:**
```
Workflow: ingest → transform → validate → load

Execution:
1. ingest: SUCCESS (committed to DB)
2. transform: SUCCESS (committed to DB)
3. validate: SUCCESS (committed to DB)
4. load: FAILED (committed to DB)

Problem discovered: transform output was corrupt
Desired action: Rollback to ingest, re-run from there

Current capability: Can only resume from load
                   Cannot re-run transform without manual intervention
```

**Impact:**
- **No recovery from mid-workflow corruption**
- **Manual intervention required** for complex rollbacks
- **Data integrity risk** - Partial workflow state persisted
- **Operational overhead** - Must manually mark jobs for re-run

**Recommended Solution:**
1. **Checkpoint-based commits:** Only commit after successful checkpoints
2. **Rollback command:** `--rollback-to <JOB_ID>` to mark jobs as pending from that point
3. **Transaction mode:** Optional atomic workflow mode (all or nothing)

---

### Issue #7: Dependency Validation Gap on Resume

**Severity:** HIGH
**Location:** `state_manager.py:157-228`, `queue_manager.py:136-213`

**Problem:** When resuming with skipped jobs, no validation that:
1. Skipped jobs' dependencies were actually satisfied
2. Dependencies haven't been removed from config
3. Dependency chain is still valid

**Scenario 1: Removed Dependency**
```
Original config (Attempt 1):
{
  "jobs": [
    {"id": "job1", "dependencies": []},
    {"id": "job2", "dependencies": ["job1"]},
    {"id": "job3", "dependencies": ["job2"]}
  ]
}

Attempt 1 result:
- job1: SUCCESS
- job2: FAILED
- job3: PENDING (never ran)

Modified config (before resume):
{
  "jobs": [
    {"id": "job2", "dependencies": []},  // Removed job1!
    {"id": "job3", "dependencies": ["job2"]}
  ]
}

Resume:
- job1 no longer in config
- job2 resumes without checking job1 satisfied
- Dependency chain broken, no validation
```

**Scenario 2: Changed Dependencies**
```
Original: job3 depends on [job1, job2]
Modified: job3 depends on [job1, job2, job4]  // Added job4

Resume:
- job4 never ran (new dependency)
- job3 queued because job1, job2 successful
- job3 missing job4's output → FAILS
```

**Current Code Issue:**
```python
# queue_manager.py:186-199
def queue_initial_jobs():
    for job in jobs:
        if all(dep in (completed_jobs | skip_jobs) for dep in job.dependencies):
            queue(job)

# Problem: Uses dependencies from CURRENT config
# Doesn't validate against ORIGINAL attempt's dependency graph
```

**Impact:**
- **Silent dependency violations**
- **Workflows execute with missing inputs**
- **Unpredictable failures**
- **Difficult debugging**

**Recommended Solution:**
1. Store dependency graph per attempt
2. Validate current config dependencies match original
3. Warn or fail if dependency changes detected
4. Provide `--force-new-dependencies` flag for intentional changes

---

## Edge Cases & Scenarios

### Scenario 1: Restarting with Different Config

**Setup:**
```
Attempt 1:
- Config defines: 10 jobs
- Result: 5 SUCCESS, 5 FAILED
- total_jobs in run_summary: 10

User modifies config, adds 2 new jobs:
- Config now defines: 12 jobs

Attempt 2:
- Resume with --resume-from
```

**Problem:**
```python
# execution_history_manager.py:321-329
if failed_jobs > 0:
    status = 'FAILED'
elif successful_jobs == total_jobs:  # ← total_jobs still 10!
    status = 'SUCCESS'
elif successful_jobs > 0:
    status = 'PARTIAL'
```

**Result:**
- Even if all 12 jobs succeed, status calculation uses old total_jobs=10
- Status might show 'PARTIAL' instead of 'SUCCESS'
- Metrics are incorrect

---

### Scenario 2: Parallel Execution Race Condition

**Location:** `execution_orchestrator.py:209-327`

**Setup:**
```python
# Parallel mode with shared mutable state
completed_jobs = set()
skip_jobs = set()

# Thread 1 and Thread 2 both check dependencies simultaneously
```

**Potential Race:**
```
Time  Thread 1 (job2)              Thread 2 (job3)
----  -------------------------    -------------------------
T1    Check job2 deps
T2    job1 in completed? YES       Check job3 deps
T3    Queue job2                   job2 in completed? NO
T4                                 job1 in completed? YES
T5    Complete job2                Queue job3 (MISSING job2!)
T6    Add job2 to completed
```

**Note:** Currently mitigated by proper locking, but design is fragile with mutable shared state.

---

### Scenario 3: Midstream Start with Changed Dependencies

**Setup:**
```
Original workflow (Attempt 1):
job1 → job2 → job3 → job4

Modified workflow:
job1 → job2 → job3A → job3B → job4
           ↘           ↗
```

**User Action:**
```bash
# Manually mark jobs successful to start from job3A
executioner.py --mark-success -r 123 -j job1,job2

# Resume
executioner.py --resume-from 123
```

**Problem:**
- Old attempt has job3, new config has job3A, job3B
- Which jobs execute?
- What happens to old job3 status?
- Dependencies changed but no validation

---

### Scenario 4: Concurrent Resumes of Same Run ID

**Setup:**
```bash
# Terminal 1
executioner.py --resume-from 123

# Terminal 2 (simultaneously)
executioner.py --resume-from 123
```

**Current Behavior:**
```python
# Both processes:
attempt_id = get_next_attempt_id(123)  # Both get attempt_id=2

# Process 1
create_run_summary(run_id=123, attempt_id=2)  # SUCCESS

# Process 2
create_run_summary(run_id=123, attempt_id=2)  # UNIQUE CONSTRAINT VIOLATED
# Catches exception, silently continues
```

**Problem:**
- Both processes run with same attempt_id
- Job statuses overwrite each other
- Race condition in ON CONFLICT DO UPDATE
- Final state is unpredictable

---

### Scenario 5: Resume After Job Removal

**Setup:**
```
Attempt 1 jobs: [job1, job2, job3, job4, job5]
Result: job1-3 SUCCESS, job4-5 FAILED

Modified config (removed job4):
New jobs: [job1, job2, job3, job5]

Resume:
```

**What Happens:**
```python
# state_manager.py:setup_resume()
previous_jobs = get_previous_run_status(123)
# Returns: {job1: SUCCESS, job2: SUCCESS, job3: SUCCESS,
#           job4: FAILED, job5: FAILED}

config_jobs = [job1, job2, job3, job5]

# job4 in previous but not in config
# Warning logged but execution continues
# job5 depends on job4 (in old config)
# Dependency validation may fail or pass incorrectly
```

---

## Detailed Technical Analysis

### 1. Run ID Lifecycle

**Location:** `execution_history_manager.py:20-33`, `state_manager.py:64-86`

#### Fresh Run (New run_id)

```python
def get_new_run_id():
    """Generate new run ID"""
    cursor.execute("""
        SELECT MAX(run_id) FROM (
            SELECT run_id FROM job_history
            UNION
            SELECT run_id FROM run_summary
        )
    """)
    max_run_id = cursor.fetchone()[0] or 0
    return max_run_id + 1
```

**Behavior:**
- Queries both `job_history` and `run_summary` tables
- Returns highest run_id + 1
- Starts at 1 if no prior runs

#### Resume Run (Reuse run_id)

```python
def initialize_run(self, resume_run_id=None):
    if resume_run_id:
        self.run_id = resume_run_id  # ← REUSE
        self.attempt_id = get_next_attempt_id(resume_run_id)
    else:
        self.run_id = get_new_run_id()
        self.attempt_id = 1
```

**Attempt ID Retrieval:**
```python
def get_next_attempt_id(run_id):
    """Get next attempt ID for a run"""
    cursor.execute(
        "SELECT MAX(attempt_id) FROM run_summary WHERE run_id=?",
        (run_id,)
    )
    max_attempt = cursor.fetchone()[0] or 0
    return max_attempt + 1
```

**Example Flow:**
```
Fresh run:     run_id=5, attempt_id=1
First resume:  run_id=5, attempt_id=2
Second resume: run_id=5, attempt_id=3
Third resume:  run_id=5, attempt_id=4
```

---

### 2. Database Schema for Run/Attempt Tracking

**Location:** `db/sqlite_connection.py` (migrations 7-8)

#### run_summary Table

```sql
CREATE TABLE run_summary (
    run_id INTEGER NOT NULL,
    attempt_id INTEGER NOT NULL,
    application_name TEXT,
    start_time TEXT,
    end_time TEXT,
    status TEXT,
    total_jobs INTEGER,
    successful_jobs INTEGER,
    failed_jobs INTEGER,
    skipped_jobs INTEGER,
    PRIMARY KEY (run_id, attempt_id)
);
```

**Key Points:**
- Composite primary key: `(run_id, attempt_id)`
- Each resume creates new row with same run_id, incremented attempt_id
- Tracks aggregate statistics per attempt

#### job_history Table

```sql
CREATE TABLE job_history (
    run_id INTEGER NOT NULL,
    attempt_id INTEGER NOT NULL,
    id TEXT NOT NULL,
    status TEXT,
    start_time TEXT,
    end_time TEXT,
    duration REAL,
    exit_code INTEGER,
    last_exit_code INTEGER,
    retry_count INTEGER,
    retry_history TEXT,
    PRIMARY KEY (run_id, attempt_id, id)
);
```

**Key Points:**
- Composite primary key: `(run_id, attempt_id, id)`
- Each job execution creates separate row per attempt
- `retry_history` stored as JSON TEXT
- `last_exit_code` column exists but unused (Issue #5)

---

### 3. History Aggregation on Resume

**Location:** `execution_history_manager.py:82-114`

#### Get Previous Run Status

```python
def get_previous_run_status(run_id):
    """Get latest status for each job across all attempts"""

    # Step 1: Get latest attempt_id for each job
    cursor.execute("""
        SELECT id, status, MAX(attempt_id) as latest_attempt
        FROM job_history
        WHERE run_id = ?
        GROUP BY id
    """, (run_id,))

    # Step 2: Fetch actual status from that attempt
    job_statuses = {}
    for job_id, _, latest_attempt in cursor.fetchall():
        cursor.execute("""
            SELECT status
            FROM job_history
            WHERE run_id=? AND attempt_id=? AND id=?
        """, (run_id, latest_attempt, job_id))

        status = cursor.fetchone()[0]
        job_statuses[job_id] = status

    return job_statuses
```

**Behavior:**
- Aggregates statuses across ALL previous attempts
- Uses `MAX(attempt_id)` to get most recent
- Returns: `{job_id: latest_status}`

**Example:**
```
Attempt 1: {job1: SUCCESS, job2: FAILED, job3: PENDING}
Attempt 2: {job1: SUCCESS, job2: SUCCESS, job3: FAILED}

get_previous_run_status(run_id) returns:
{job1: SUCCESS (from attempt 2),
 job2: SUCCESS (from attempt 2),
 job3: FAILED (from attempt 2)}
```

**Issue:** No audit trail showing status CHANGED from FAILED to SUCCESS.

---

### 4. Retry History Management

**Location:** `jobs/job_runner.py:96-223`

#### Retry Execution Loop

```python
def execute_with_retry(job):
    retry_history = []

    for attempt in range(job.max_retries + 1):
        try:
            result = execute_job(job)

            if result.success:
                return result  # ← Exit on success

            # Record failed attempt
            retry_history.append({
                'attempt': attempt + 1,
                'timestamp': current_time(),
                'status': result.status,
                'exit_code': result.exit_code,
                'error': result.error
            })

            # Check if should retry
            if not should_retry(result, job.retry_on_status, job.retry_on_exit_codes):
                break

            # Calculate retry delay
            delay = calculate_delay(job.retry_delay, job.retry_backoff, attempt)
            time.sleep(delay)

        except Exception as e:
            retry_history.append({...})

    # Only reached if all retries exhausted
    finally:
        update_job_status(
            retry_count=len(retry_history),
            retry_history=json.dumps(retry_history)
        )
```

**Problem:**
```python
if result.success:
    return result  # ← Exits early, never reaches finally!
```

**Result:** Successful retries don't record retry_history.

---

### 5. Dependency Handling During Resume

**Location:** `queue_manager.py:136-213`

#### Initial Job Queuing

```python
def queue_initial_jobs(self):
    """Queue jobs with no dependencies or satisfied dependencies"""

    for job in self.jobs:
        # Check if all dependencies satisfied
        if all(dep in (self.completed_jobs | self.skip_jobs)
               for dep in job.dependencies):

            # Additional check: no failed dependencies
            if not any(dep in self.failed_jobs for dep in job.dependencies):
                self.queue_job(job)
```

**Resume Behavior:**
```python
# From previous attempt
completed_jobs = {job1, job2, job3}  # SUCCESS in previous attempt
skip_jobs = set()  # Empty unless using --resume-failed-only
failed_jobs = {job4, job5}  # FAILED in previous attempt

# Current attempt
Jobs to process: [job1, job2, job3, job4, job5, job6]

Initial queue:
- job1: Skip (in completed_jobs)
- job2: Skip (in completed_jobs)
- job3: Skip (in completed_jobs)
- job4: Queue (failed, needs retry)
- job5: Queue (failed, needs retry)
- job6: Queue if depends only on job1-3, else wait
```

#### Dependent Job Queuing

```python
def queue_dependent_jobs(self, completed_job_id):
    """Queue jobs that were waiting on this job"""

    for job in self.jobs:
        if completed_job_id in job.dependencies:
            # Check all dependencies satisfied
            if all(dep in (self.completed_jobs | self.skip_jobs)
                   for dep in job.dependencies):

                # Check no failed dependencies
                if not any(dep in self.failed_jobs
                          for dep in job.dependencies):
                    self.queue_job(job)
```

**Issue:** No validation that dependencies in current config match dependencies in previous attempt.

---

### 6. Run Status Determination

**Location:** `execution_history_manager.py:321-329`

```python
def determine_run_status(successful_jobs, failed_jobs, total_jobs):
    """Determine overall run status"""

    if failed_jobs > 0:
        return 'FAILED'
    elif successful_jobs == total_jobs:
        return 'SUCCESS'
    elif successful_jobs > 0:
        return 'PARTIAL'
    else:
        return 'PENDING'
```

**Problem:**
```python
# total_jobs from run_summary is from ORIGINAL attempt
# If config changes:
original_total_jobs = 10
new_total_jobs = 12

# Status calculation uses old value
if successful_jobs == 10:  # Should be 12!
    return 'SUCCESS'
```

**Impact:** Incorrect status when jobs added/removed between attempts.

---

## Recommendations

### Priority 1: Critical Fixes

#### 1.1 Add Config Validation on Resume

**Implementation:**
```python
def validate_config_on_resume(run_id, current_config):
    """Validate current config matches previous attempt"""

    previous_jobs = get_previous_run_status(run_id)
    current_jobs = {job.id for job in current_config.jobs}

    # Check for removed jobs
    removed_jobs = set(previous_jobs.keys()) - current_jobs
    if removed_jobs:
        raise ConfigValidationError(
            f"Jobs removed from config: {removed_jobs}. "
            f"Cannot safely resume. Use --force to override."
        )

    # Check for modified job definitions
    for job in current_config.jobs:
        if job.id in previous_jobs:
            previous_def = get_job_definition(run_id, job.id)
            if job_definition_changed(job, previous_def):
                raise ConfigValidationError(
                    f"Job '{job.id}' definition changed. "
                    f"Cannot safely resume. Use --force to override."
                )

    # Check for dependency changes
    for job in current_config.jobs:
        if job.id in previous_jobs:
            previous_deps = get_job_dependencies(run_id, job.id)
            if set(job.dependencies) != set(previous_deps):
                raise ConfigValidationError(
                    f"Job '{job.id}' dependencies changed. "
                    f"Previous: {previous_deps}, Current: {job.dependencies}"
                )
```

**CLI Addition:**
```bash
# Strict mode (default)
executioner.py --resume-from 123

# Allow config changes (dangerous)
executioner.py --resume-from 123 --force
```

---

#### 1.2 Populate Exit Codes

**Implementation:**
```python
# In job_runner.py
def execute_job(job):
    result = run_command(job.command)

    # Update job status with exit code
    execution_history_manager.update_job_status(
        run_id=run_id,
        attempt_id=attempt_id,
        job_id=job.id,
        status=result.status,
        exit_code=result.exit_code,  # ← ADD THIS
        last_exit_code=result.exit_code  # ← ADD THIS
    )

    return result
```

**Update Schema:**
```python
# execution_history_manager.py
def update_job_status(self, run_id, attempt_id, job_id, status,
                     exit_code=None, last_exit_code=None, **kwargs):
    self.pending_updates.append({
        'run_id': run_id,
        'attempt_id': attempt_id,
        'id': job_id,
        'status': status,
        'exit_code': exit_code,
        'last_exit_code': last_exit_code,
        **kwargs
    })
```

---

#### 1.3 Add Native Midstream Restart

**Implementation:**
```python
# New CLI argument
parser.add_argument('--from-job', type=str,
                   help='Start execution from specific job (marks predecessors as successful)')

def handle_from_job(config, from_job_id):
    """Implement midstream restart"""

    # Validate job exists
    if from_job_id not in [j.id for j in config.jobs]:
        raise ValueError(f"Job '{from_job_id}' not found in config")

    # Build dependency graph
    graph = build_dependency_graph(config.jobs)

    # Get all predecessor jobs
    predecessors = get_all_predecessors(graph, from_job_id)

    # Validate no cycles
    if has_cycles(graph):
        raise ValueError("Cannot start midstream: circular dependencies detected")

    # Create new run with predecessors marked successful
    run_id = create_run_with_marked_jobs(
        config=config,
        marked_jobs=predecessors,
        marked_status='SUCCESS'
    )

    # Execute from target job
    execute_workflow(config, run_id=run_id, skip_jobs=predecessors)
```

**Usage:**
```bash
# Start workflow from job3 (automatically marks job1, job2 as successful)
executioner.py -c config.json --from-job job3
```

---

### Priority 2: Important Enhancements

#### 2.1 Fix Ghost Attempts

**Implementation:**
```python
# state_manager.py
def initialize_run(self, resume_run_id=None):
    if resume_run_id:
        self.run_id = resume_run_id
        self.attempt_id = get_next_attempt_id(resume_run_id)
    else:
        self.run_id = get_new_run_id()
        self.attempt_id = 1

    # DON'T create run_summary here!
    # Wait until first job starts

def on_first_job_start(self):
    """Called when first job starts executing"""
    if not self.run_summary_created:
        create_run_summary(
            run_id=self.run_id,
            attempt_id=self.attempt_id,
            application_name=self.application_name,
            start_time=current_time(),
            total_jobs=len(self.jobs)
        )
        self.run_summary_created = True
```

---

#### 2.2 Record Successful Retries

**Implementation:**
```python
# job_runner.py
def execute_with_retry(job):
    retry_history = []

    for attempt in range(job.max_retries + 1):
        result = execute_job(job)

        # Record ALL attempts, not just failures
        retry_history.append({
            'attempt': attempt + 1,
            'timestamp': current_time(),
            'status': result.status,
            'exit_code': result.exit_code,
            'success': result.success
        })

        if result.success:
            # Record retry history BEFORE returning
            update_job_status(
                retry_count=len(retry_history) - 1,  # Exclude final success
                retry_history=json.dumps(retry_history)
            )
            return result

        if not should_retry(result, job.retry_on_status, job.retry_on_exit_codes):
            break

        delay = calculate_delay(job.retry_delay, job.retry_backoff, attempt)
        time.sleep(delay)

    # All retries exhausted
    update_job_status(
        retry_count=len(retry_history),
        retry_history=json.dumps(retry_history)
    )
    return result
```

---

#### 2.3 Add Rollback Support

**Implementation:**
```python
# New CLI command
parser.add_argument('--rollback-to', type=str,
                   help='Rollback to specific job (marks it and successors as PENDING)')

def handle_rollback(run_id, rollback_job_id):
    """Rollback execution to specific job"""

    # Get dependency graph from last attempt
    graph = get_dependency_graph(run_id)

    # Get job and all successors
    jobs_to_reset = get_job_and_successors(graph, rollback_job_id)

    # Mark jobs as PENDING
    for job_id in jobs_to_reset:
        update_job_status(
            run_id=run_id,
            job_id=job_id,
            status='PENDING',
            reset_time=current_time()
        )

    logger.info(f"Rolled back {len(jobs_to_reset)} jobs to PENDING")
    logger.info(f"Jobs reset: {jobs_to_reset}")
    logger.info(f"Use --resume-from {run_id} to re-execute")
```

**Usage:**
```bash
# Rollback to job2 (marks job2, job3, job4 as PENDING)
executioner.py --rollback-to job2 -r 123

# Then resume
executioner.py --resume-from 123
```

---

### Priority 3: Monitoring & Observability

#### 3.1 Add Attempt Metadata Table

**Schema:**
```sql
CREATE TABLE attempt_metadata (
    run_id INTEGER NOT NULL,
    attempt_id INTEGER NOT NULL,
    config_hash TEXT,
    config_snapshot TEXT,  -- JSON snapshot of config
    triggered_by TEXT,     -- user, system, scheduler
    trigger_reason TEXT,   -- manual_resume, auto_retry, scheduled
    parent_attempt_id INTEGER,
    created_at TEXT,
    PRIMARY KEY (run_id, attempt_id),
    FOREIGN KEY (run_id, attempt_id) REFERENCES run_summary(run_id, attempt_id)
);
```

**Benefits:**
- Track which config version each attempt used
- Detect config changes between attempts
- Audit trail for compliance
- Debug attempt history

---

#### 3.2 Add Dependency Validation Logs

**Implementation:**
```python
def validate_dependencies_on_resume(run_id, current_config):
    """Validate and log dependency changes"""

    validation_log = []

    for job in current_config.jobs:
        # Get previous dependencies
        previous_deps = get_job_dependencies(run_id, job.id)
        current_deps = job.dependencies

        # Check for changes
        added_deps = set(current_deps) - set(previous_deps)
        removed_deps = set(previous_deps) - set(current_deps)

        if added_deps or removed_deps:
            validation_log.append({
                'job_id': job.id,
                'added_dependencies': list(added_deps),
                'removed_dependencies': list(removed_deps),
                'timestamp': current_time()
            })

    if validation_log:
        log_dependency_changes(run_id, validation_log)

        if strict_mode:
            raise ConfigValidationError(
                f"Dependency changes detected: {validation_log}"
            )
```

---

#### 3.3 Improve Resume Status Display

**Implementation:**
```python
def display_resume_status(run_id):
    """Display detailed resume status"""

    attempts = get_all_attempts(run_id)

    print(f"Run ID: {run_id}")
    print(f"Total Attempts: {len(attempts)}")
    print()

    for attempt in attempts:
        print(f"Attempt {attempt.attempt_id}:")
        print(f"  Started: {attempt.start_time}")
        print(f"  Status: {attempt.status}")
        print(f"  Jobs: {attempt.successful_jobs}/{attempt.total_jobs} successful")

        if attempt.failed_jobs > 0:
            failed_job_ids = get_failed_job_ids(run_id, attempt.attempt_id)
            print(f"  Failed: {failed_job_ids}")

        print()

    # Show what will happen on resume
    next_attempt_id = len(attempts) + 1
    jobs_to_retry = get_jobs_to_retry(run_id)
    jobs_to_skip = get_jobs_to_skip(run_id)

    print(f"Next Attempt ({next_attempt_id}):")
    print(f"  Will retry: {jobs_to_retry}")
    print(f"  Will skip: {jobs_to_skip}")
```

**Usage:**
```bash
# Show resume status before resuming
executioner.py --show-resume-status -r 123

# Then decide to resume
executioner.py --resume-from 123
```

---

### Priority 4: Safety Features

#### 4.1 Prevent Concurrent Resumes

**Implementation:**
```python
def acquire_resume_lock(run_id, attempt_id):
    """Prevent concurrent resumes of same run"""

    lock_file = f"/tmp/executioner_lock_{run_id}_{attempt_id}.lock"

    try:
        # Try to create lock file (exclusive)
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()}\n{current_time()}".encode())
        os.close(fd)

        return lock_file
    except FileExistsError:
        # Lock already exists, check if process is alive
        with open(lock_file) as f:
            pid = int(f.readline().strip())

        if process_is_running(pid):
            raise ConcurrentResumeError(
                f"Run {run_id} is already being resumed by process {pid}"
            )
        else:
            # Stale lock, remove and retry
            os.remove(lock_file)
            return acquire_resume_lock(run_id, attempt_id)

def release_resume_lock(lock_file):
    """Release resume lock"""
    if os.path.exists(lock_file):
        os.remove(lock_file)
```

---

#### 4.2 Add Dry-Run Mode for Resume

**Implementation:**
```python
parser.add_argument('--dry-run', action='store_true',
                   help='Show what would be executed without running')

def dry_run_resume(run_id, config):
    """Show what would happen on resume without executing"""

    # Load previous status
    previous_status = get_previous_run_status(run_id)

    # Determine jobs to retry
    jobs_to_retry = []
    jobs_to_skip = []

    for job in config.jobs:
        if job.id in previous_status:
            if previous_status[job.id] in ['FAILED', 'ERROR', 'TIMEOUT']:
                jobs_to_retry.append(job.id)
            else:
                jobs_to_skip.append(job.id)
        else:
            jobs_to_retry.append(job.id)  # New job

    print("DRY RUN: Resume from run", run_id)
    print()
    print(f"Jobs to retry ({len(jobs_to_retry)}):")
    for job_id in jobs_to_retry:
        print(f"  - {job_id} ({previous_status.get(job_id, 'NEW')})")
    print()
    print(f"Jobs to skip ({len(jobs_to_skip)}):")
    for job_id in jobs_to_skip:
        print(f"  - {job_id} ({previous_status[job_id]})")
    print()

    # Validate config changes
    try:
        validate_config_on_resume(run_id, config)
        print("✓ Config validation passed")
    except ConfigValidationError as e:
        print(f"✗ Config validation failed: {e}")

    # Check dependencies
    try:
        validate_dependencies(config, previous_status)
        print("✓ Dependency validation passed")
    except DependencyValidationError as e:
        print(f"✗ Dependency validation failed: {e}")
```

**Usage:**
```bash
# See what would happen on resume
executioner.py --resume-from 123 --dry-run

# Actually resume
executioner.py --resume-from 123
```

---

## Test Scenarios

### Test Scenario 1: Basic Resume After Partial Failure

**Status:** ✅ Should work

**Setup:**
```json
{
  "jobs": [
    {"id": "job1", "command": "echo job1", "dependencies": []},
    {"id": "job2", "command": "echo job2", "dependencies": ["job1"]},
    {"id": "job3", "command": "exit 1", "dependencies": ["job2"]},
    {"id": "job4", "command": "echo job4", "dependencies": ["job3"]}
  ]
}
```

**Test Steps:**
```bash
# Run workflow
executioner.py -c test_resume.json

# Expected:
# - job1: SUCCESS
# - job2: SUCCESS
# - job3: FAILED (exit 1)
# - job4: SKIPPED (dependency failed)

# Fix job3 in config
# Change: {"id": "job3", "command": "echo job3", ...}

# Resume
executioner.py -c test_resume.json --resume-from <RUN_ID>

# Expected:
# - job1: SKIPPED (already successful)
# - job2: SKIPPED (already successful)
# - job3: RETRY (fixed command)
# - job4: EXECUTE (dependency now satisfied)
```

**Verify:**
- Same run_id used
- Attempt ID incremented
- Successful jobs skipped
- Failed jobs retried
- Downstream jobs executed

---

### Test Scenario 2: Resume with Modified Config

**Status:** ⚠️ Undefined behavior (needs fix)

**Setup:**
```json
// Original config (Attempt 1)
{
  "jobs": [
    {"id": "extract", "command": "python extract_v1.py", "dependencies": []},
    {"id": "transform", "command": "python transform.py", "dependencies": ["extract"]},
    {"id": "load", "command": "exit 1", "dependencies": ["transform"]}
  ]
}
```

**Test Steps:**
```bash
# Run workflow
executioner.py -c workflow.json

# Expected:
# - extract: SUCCESS (runs extract_v1.py)
# - transform: SUCCESS
# - load: FAILED

# Modify config - change extract command
# New: {"id": "extract", "command": "python extract_v2.py", ...}

# Resume WITHOUT fixing issue #2
executioner.py -c workflow.json --resume-from <RUN_ID>
```

**Current Behavior:**
- Warning logged but continues
- Unclear which extract version's data transform used
- Load retries but may expect v2 data while having v1

**After Fix:**
```bash
# Resume with validation
executioner.py -c workflow.json --resume-from <RUN_ID>
# ERROR: Job 'extract' definition changed. Cannot resume.

# Force resume (dangerous)
executioner.py -c workflow.json --resume-from <RUN_ID> --force
# WARNING: Config changed, forcing resume anyway
```

---

### Test Scenario 3: Midstream Start Without Native Support

**Status:** ❌ Requires manual workaround (needs fix)

**Setup:**
```json
{
  "jobs": [
    {"id": "job1", "command": "echo job1", "dependencies": []},
    {"id": "job2", "command": "echo job2", "dependencies": ["job1"]},
    {"id": "job3", "command": "echo job3", "dependencies": ["job2"]},
    {"id": "job4", "command": "echo job4", "dependencies": ["job3"]}
  ]
}
```

**Goal:** Start from job3 (skip job1, job2)

**Current Process:**
```bash
# Create fresh run
executioner.py -c workflow.json
# Let's say run_id = 123

# Manually mark jobs successful
executioner.py --mark-success -r 123 -j job1,job2

# Resume
executioner.py -c workflow.json --resume-from 123

# Executes: job3, job4
```

**Problems with Current Approach:**
- Requires knowing exact job IDs
- Easy to make mistakes (forget a dependency)
- No validation
- Multiple commands required

**After Fix (Recommendation 1.3):**
```bash
# Native midstream start
executioner.py -c workflow.json --from-job job3

# Automatically:
# - Identifies job3's dependencies: [job1, job2]
# - Validates dependency chain
# - Marks job1, job2 as SUCCESS
# - Executes job3, job4
```

---

### Test Scenario 4: Resume After Job Removal

**Status:** ⚠️ Likely breaks (needs validation)

**Setup:**
```json
// Original config
{
  "jobs": [
    {"id": "job1", "command": "echo job1", "dependencies": []},
    {"id": "job2", "command": "echo job2", "dependencies": ["job1"]},
    {"id": "job3", "command": "exit 1", "dependencies": ["job2"]},
    {"id": "job4", "command": "echo job4", "dependencies": ["job3"]}
  ]
}
```

**Test Steps:**
```bash
# Run workflow
executioner.py -c workflow.json

# Result:
# - job1: SUCCESS
# - job2: SUCCESS
# - job3: FAILED
# - job4: SKIPPED

# Remove job3 from config
// Modified config
{
  "jobs": [
    {"id": "job1", "command": "echo job1", "dependencies": []},
    {"id": "job2", "command": "echo job2", "dependencies": ["job1"]},
    {"id": "job4", "command": "echo job4", "dependencies": ["job2"]}
  ]
}

# Resume
executioner.py -c workflow.json --resume-from <RUN_ID>
```

**Expected Current Behavior:**
- Warning: "Job count mismatch"
- Continues anyway
- job4 dependency changed from [job3] to [job2]
- job4 may execute (job2 was successful)
- But job4 might expect job3's output!

**After Fix:**
```bash
# With validation (Recommendation 1.1)
executioner.py -c workflow.json --resume-from <RUN_ID>
# ERROR: Job 'job3' removed from config. Cannot resume.

# Verify:
Previous jobs: [job1, job2, job3, job4]
Current jobs:  [job1, job2, job4]
Removed:       [job3]
```

---

### Test Scenario 5: Concurrent Resumes

**Status:** ⚠️ Race condition (needs locking)

**Setup:**
```bash
# Terminal 1
executioner.py -c workflow.json --resume-from 123

# Terminal 2 (simultaneously)
executioner.py -c workflow.json --resume-from 123
```

**Current Behavior:**
```
Both processes:
1. Get next_attempt_id = 2
2. Both try to create run_summary(run_id=123, attempt_id=2)
3. Process 1: SUCCESS
4. Process 2: UNIQUE CONSTRAINT violation, silently continues
5. Both execute jobs with attempt_id=2
6. Job status updates race (ON CONFLICT DO UPDATE)
7. Final state unpredictable
```

**After Fix (Recommendation 4.1):**
```bash
# Process 1
executioner.py -c workflow.json --resume-from 123
# Acquires lock

# Process 2
executioner.py -c workflow.json --resume-from 123
# ERROR: Run 123 is already being resumed by process 12345
```

---

### Test Scenario 6: Exit Code Validation

**Status:** ❌ Broken (exit codes not populated)

**Setup:**
```json
{
  "jobs": [
    {
      "id": "flaky_job",
      "command": "python flaky_script.py",
      "retry_on_exit_codes": [1, 2],
      "max_retries": 3
    }
  ]
}
```

**Test Steps:**
```bash
# Run workflow
executioner.py -c workflow.json

# flaky_script.py exits with code 1 (should retry)
# But on attempt 1, all retries exhausted

# Fix script to be less flaky

# Resume
executioner.py -c workflow.json --resume-from <RUN_ID>
```

**Current Behavior:**
```python
# get_last_exit_code(run_id, 'flaky_job')
# Returns: NULL (exit code never populated!)

# Retry logic:
if last_exit_code in retry_on_exit_codes:  # NULL in [1, 2] → False
    should_retry = True
else:
    should_retry = False  # ← Takes this path

# Falls back to status-based retry
```

**After Fix (Recommendation 1.2):**
```python
# get_last_exit_code(run_id, 'flaky_job')
# Returns: 1

# Retry logic:
if last_exit_code in retry_on_exit_codes:  # 1 in [1, 2] → True
    should_retry = True  # ← Correct!
```

---

### Test Scenario 7: Retry History for Successful Jobs

**Status:** ❌ Lost (retry history not recorded on success)

**Setup:**
```json
{
  "jobs": [
    {
      "id": "retry_job",
      "command": "python flaky_script.py",
      "max_retries": 5,
      "retry_delay": 2
    }
  ]
}
```

**Test Steps:**
```bash
# Run workflow
# flaky_script.py behavior:
# - Attempt 1: FAILED (exit 1)
# - Attempt 2: FAILED (exit 1)
# - Attempt 3: SUCCESS (exit 0)

executioner.py -c workflow.json
```

**Current Behavior:**
```sql
SELECT retry_count, retry_history
FROM job_history
WHERE id='retry_job';

-- Results:
-- retry_count: NULL
-- retry_history: NULL

-- History lost because job succeeded on attempt 3!
```

**After Fix (Recommendation 2.2):**
```sql
SELECT retry_count, retry_history
FROM job_history
WHERE id='retry_job';

-- Results:
-- retry_count: 2
-- retry_history: [
--   {"attempt": 1, "status": "FAILED", "exit_code": 1},
--   {"attempt": 2, "status": "FAILED", "exit_code": 1},
--   {"attempt": 3, "status": "SUCCESS", "exit_code": 0}
-- ]
```

---

### Test Scenario 8: Rollback to Earlier Job

**Status:** ❌ Not supported (needs feature)

**Setup:**
```json
{
  "jobs": [
    {"id": "ingest", "command": "python ingest.py", "dependencies": []},
    {"id": "transform", "command": "python transform.py", "dependencies": ["ingest"]},
    {"id": "validate", "command": "python validate.py", "dependencies": ["transform"]},
    {"id": "load", "command": "python load.py", "dependencies": ["validate"]}
  ]
}
```

**Scenario:**
```bash
# Run workflow
executioner.py -c workflow.json

# Result:
# - ingest: SUCCESS
# - transform: SUCCESS (but output was corrupt!)
# - validate: SUCCESS (validation missed corruption)
# - load: FAILED (detected corruption)

# Problem discovered: transform logic has bug
# Need to re-run from transform
```

**Current Process:**
```bash
# No native rollback, must manually intervene
# Option 1: Mark transform as failed manually (requires DB access)
sqlite3 jobs_history.db
UPDATE job_history SET status='FAILED' WHERE id='transform' AND run_id=123;

# Option 2: Use --mark-success workaround
# (but this is for forward progress, not rollback)
```

**After Fix (Recommendation 2.3):**
```bash
# Rollback to transform
executioner.py --rollback-to transform -r 123

# Output:
# Rolled back 3 jobs to PENDING: transform, validate, load
# Use --resume-from 123 to re-execute

# Resume
executioner.py -c workflow.json --resume-from 123

# Executes:
# - ingest: SKIPPED (still successful)
# - transform: RETRY (marked PENDING)
# - validate: RETRY (marked PENDING)
# - load: RETRY (marked PENDING)
```

---

## Summary Table: Critical Findings

| Area | Current Behavior | Status | Priority |
|------|-----------------|--------|----------|
| **Job Retry** | Built-in retry within single attempt | ✅ Works | P2 (Enhancement) |
| **Run Resume** | Reuses run_id, increments attempt_id | ✅ Good design | P2 (Fix ghost attempts) |
| **Midstream Start** | Manual --mark-success workaround | ❌ Error-prone | P1 (Critical) |
| **Dependency Handling** | Uses latest status across attempts | ⚠️ No audit trail | P1 (Critical) |
| **Config Validation** | Warns but continues on changes | ❌ Dangerous | P1 (Critical) |
| **Exit Code Tracking** | Column exists but not populated | ❌ Broken | P1 (Critical) |
| **History Persistence** | Immediate commit on job completion | ⚠️ No rollback | P2 (Enhancement) |
| **Composite Key Design** | (run_id, attempt_id, job_id) | ✅ Excellent | N/A |
| **Retry History** | Only captures failures | ⚠️ Incomplete | P2 (Enhancement) |
| **Concurrent Resume** | No locking mechanism | ⚠️ Race condition | P4 (Safety) |
| **Ghost Attempts** | Empty attempts created on early failure | ⚠️ DB pollution | P2 (Enhancement) |
| **Rollback Support** | Not supported | ❌ Missing feature | P2 (Enhancement) |

---

## Implementation Roadmap

### Phase 1: Critical Fixes (Weeks 1-2)

1. ✅ **Config Validation on Resume** (Recommendation 1.1)
   - Files: `state_manager.py`, `execution_history_manager.py`
   - Add validation function
   - Add `--force` flag for overrides
   - Test with scenario 2

2. ✅ **Populate Exit Codes** (Recommendation 1.2)
   - Files: `job_runner.py`, `execution_history_manager.py`
   - Update `update_job_status()` signature
   - Pass exit codes from job execution
   - Test with scenario 6

3. ✅ **Native Midstream Restart** (Recommendation 1.3)
   - Files: `executioner.py`, `state_manager.py`
   - Add `--from-job` argument
   - Implement dependency graph traversal
   - Validate predecessors
   - Test with scenario 3

### Phase 2: Important Enhancements (Weeks 3-4)

4. ✅ **Fix Ghost Attempts** (Recommendation 2.1)
   - Files: `state_manager.py`
   - Defer run_summary creation
   - Create on first job start
   - Test edge cases

5. ✅ **Record Successful Retries** (Recommendation 2.2)
   - Files: `job_runner.py`
   - Update retry history recording
   - Record all attempts, not just failures
   - Test with scenario 7

6. ✅ **Add Rollback Support** (Recommendation 2.3)
   - Files: `executioner.py`, `execution_history_manager.py`
   - Add `--rollback-to` command
   - Implement successor traversal
   - Test with scenario 8

### Phase 3: Monitoring & Observability (Weeks 5-6)

7. ✅ **Add Attempt Metadata Table** (Recommendation 3.1)
   - Files: `db/sqlite_connection.py`, `execution_history_manager.py`
   - Create migration for new table
   - Store config hash and snapshot
   - Track attempt lineage

8. ✅ **Add Dependency Validation Logs** (Recommendation 3.2)
   - Files: `state_manager.py`, `queue_manager.py`
   - Log dependency changes
   - Create audit trail
   - Add validation reports

9. ✅ **Improve Resume Status Display** (Recommendation 3.3)
   - Files: `executioner.py`
   - Add `--show-resume-status` command
   - Display attempt history
   - Show next attempt plan

### Phase 4: Safety Features (Weeks 7-8)

10. ✅ **Prevent Concurrent Resumes** (Recommendation 4.1)
    - Files: `state_manager.py`
    - Implement file-based locking
    - Check for stale locks
    - Test with scenario 5

11. ✅ **Add Dry-Run Mode** (Recommendation 4.2)
    - Files: `executioner.py`, `state_manager.py`
    - Add `--dry-run` flag
    - Display execution plan
    - Run validations without executing

---

## Conclusion

The Executioner restart logic has a solid foundation with the `run_id`/`attempt_id` design, but several critical gaps exist:

**Strengths:**
- Well-designed composite key schema
- Built-in job retry with configurable backoff
- Two resume modes (normal and failed-only)
- Dependency resolution during resume

**Critical Issues:**
1. No native midstream restart - requires manual, error-prone workaround
2. Config changes not validated - can lead to silent data corruption
3. Exit codes not populated - breaks retry logic
4. No rollback support - can't recover from mid-workflow corruption

**Recommended Actions:**
1. Implement Priority 1 fixes immediately (config validation, exit codes, midstream restart)
2. Add rollback support and fix ghost attempts (Priority 2)
3. Enhance observability with attempt metadata (Priority 3)
4. Add safety features like dry-run mode (Priority 4)

**Risk Assessment:**
- **Current Risk:** MEDIUM-HIGH for production use
- **After P1 Fixes:** LOW for production use
- **After All Fixes:** VERY LOW, production-ready with excellent auditability

---

## Appendix: File Locations Reference

| Component | File Path | Line Numbers |
|-----------|-----------|--------------|
| Main Execution | `executioner.py` | 719-733 (resume) |
| Job Runner | `jobs/job_runner.py` | 96-200 (retry), 209-223 (history) |
| History Manager | `jobs/execution_history_manager.py` | 20-44 (run_id), 82-114 (status), 765-794 (exit code) |
| State Manager | `jobs/state_manager.py` | 64-86 (init), 157-228 (resume) |
| Queue Manager | `jobs/queue_manager.py` | 136-213 (dependency) |
| Orchestrator | `jobs/execution_orchestrator.py` | 114-131, 165-183 (validation) |
| Database Schema | `db/sqlite_connection.py` | Migrations 7-8 |

---

**Document Version:** 1.0
**Last Updated:** 2026-01-08
**Reviewed By:** Claude Code Analysis Agent
