# Race Condition and Parallel Execution Fixes

## Issues Identified

1. **Job Submission Race Condition**
   - **Problem**: Job state was checked inside a lock, but submission happened outside the lock
   - **Risk**: Same job could be submitted multiple times by different threads
   - **Location**: `jobs/executioner.py:785-792`

2. **Exit Code Not Captured**
   - **Problem**: Exit code was never propagated from subprocess to retry logic
   - **Risk**: Retry decisions couldn't use exit codes properly
   - **Location**: `jobs/job_runner.py:95-108`

3. **Non-deterministic Output Order**
   - **Status**: This is expected behavior in parallel execution
   - **Note**: Jobs complete in different orders, leading to different log output

## Fixes Applied

### 1. Fixed Job Submission Race Condition
```python
# Before: submission outside lock
if should_submit:
    future = self.executor.submit(self._execute_job, job_id)
    with self.lock:
        pending_futures.add(future)
        # ...

# After: atomic submission inside lock
if should_submit:
    with self.lock:
        # Double-check the job hasn't been submitted
        if job_id in self.active_jobs:
            continue
        future = self.executor.submit(self._execute_job, job_id)
        pending_futures.add(future)
        # ...
```

### 2. Fixed Exit Code Capture
```python
# Added exit code tracking
self.last_exit_code = None  # In _run_command

# Capture exit code after process completes
self.last_exit_code = exit_code

# Retrieve exit code in retry logic
exit_code = getattr(self, 'last_exit_code', None)
```

## Testing Results

Created comprehensive parallel execution tests:
- `parallel_race_test.json`: Tests fast job completion and dependency chains
- `parallel_stress_test.json`: Tests with many jobs and complex dependencies  
- `parallel_failure_race_test.json`: Tests failure handling in parallel execution

Testing revealed:
- ✅ No job duplication or missing jobs
- ✅ Dependencies correctly respected
- ✅ Failures properly propagate to dependent jobs
- ⚠️ Output order varies (expected in parallel execution)

## Remaining Considerations

1. **Output Ordering**: If deterministic output is needed, consider:
   - Adding job completion timestamps
   - Buffering output and sorting by job order
   - Using `--sequential` flag for deterministic execution

2. **Performance**: The additional lock check adds minimal overhead but ensures correctness

3. **Monitoring**: Consider adding metrics for:
   - Jobs queued vs submitted
   - Lock contention time
   - Worker utilization

## Files Modified
- `/home/sjoshi/claudelab/executioner/jobs/executioner.py`
- `/home/sjoshi/claudelab/executioner/jobs/job_runner.py`