# Resume/Restart User Experience Improvements

## Current Issues

### 1. No Way to List Previous Runs
**Problem**: Users must remember or find run IDs manually. There's no `--list-runs` or `--history` command.

**Current workflow**:
- User runs executioner → Gets run ID in output
- User must save/remember this ID
- No way to query past runs or their status

**Impact**: Makes resuming difficult, especially after system restarts or when multiple runs happen.

### 2. Limited Run Information
**Problem**: When a run completes/fails, the summary doesn't prominently show:
- How to resume this specific run
- What the run ID is for future reference
- Which jobs can be resumed

**Current output**:
```
========================================
           EXECUTION SUMMARY
========================================
Application: data_pipeline
Run ID: 246
Status: FAILED
...
```

**Missing**: "To resume this run, use: --resume-from 246"

### 3. No Run History Query Options
**Problem**: Can't query runs by:
- Date/time range
- Application name
- Status (failed/successful)
- Partial completion

### 4. Resume Error Messages
**Problem**: When resuming with invalid run ID:
```
No job history found for run ID 999. Starting fresh.
```
This doesn't help users find valid run IDs.

### 5. No Dry-Run for Resume
**Problem**: Can't preview what would happen with `--resume-from X --dry-run`

## Proposed Improvements

### 1. Add --list-runs Command
```bash
executioner.py --list-runs [--last N] [--status STATUS] [--app APP]
```

Example output:
```
Recent Execution History:
=======================
Run ID | Application      | Status    | Start Time          | Duration | Completed/Total
-------|------------------|-----------|---------------------|----------|----------------
  250  | data_pipeline    | SUCCESS   | 2025-05-23 10:15:00 | 00:05:23 | 8/8
  249  | data_pipeline    | FAILED    | 2025-05-23 09:45:00 | 00:02:15 | 5/8
  248  | batch_processor  | SUCCESS   | 2025-05-23 09:00:00 | 00:15:42 | 12/12
  247  | data_pipeline    | FAILED    | 2025-05-23 08:30:00 | 00:01:05 | 2/8
  246  | data_pipeline    | FAILED    | 2025-05-23 08:00:00 | 00:00:45 | 0/8

To resume a failed run: executioner.py -c <config> --resume-from <RUN_ID>
To see details: executioner.py --show-run <RUN_ID>
```

### 2. Add --show-run Command
```bash
executioner.py --show-run 249
```

Example output:
```
Run Details for ID 249:
======================
Application: data_pipeline
Status: FAILED
Start Time: 2025-05-23 09:45:00
End Time: 2025-05-23 09:47:15
Duration: 00:02:15

Job Status:
-----------
✓ download_data     - SUCCESS (00:00:30)
✓ validate_data     - SUCCESS (00:00:45)
✓ transform_part1   - SUCCESS (00:00:20)
✗ transform_part2   - FAILED  (00:00:30) - Exit code: 1
- merge_results     - SKIPPED (dependency failed)
- generate_report   - SKIPPED (dependency failed)
- send_notification - SKIPPED (dependency failed)
- cleanup           - SKIPPED (dependency failed)

Failed Job Log Preview (transform_part2):
-----------------------------------------
ERROR: Unable to process data file
FileNotFoundError: /data/part2_input.csv

To resume all remaining jobs:
  executioner.py -c data_pipeline.json --resume-from 249

To resume only failed jobs:
  executioner.py -c data_pipeline.json --resume-from 249 --resume-failed-only
```

### 3. Improve Execution Summary
Add resume instructions to the summary:

```
========================================
           EXECUTION SUMMARY
========================================
Application: data_pipeline
Run ID: 249
Status: FAILED
...

Failed Jobs:
  - transform_part2: Data transformation failed
      Reason: Exit code 1
      Log: ./logs/executioner.data_pipeline.job-transform_part2.run-249.log

RESUME OPTIONS:
===============
To resume this run (all incomplete jobs):
  executioner.py -c data_pipeline.json --resume-from 249

To retry only failed jobs:
  executioner.py -c data_pipeline.json --resume-from 249 --resume-failed-only

To view this run details later:
  executioner.py --show-run 249
```

### 4. Add Resume Preview
Support `--dry-run` with `--resume-from`:

```bash
executioner.py -c config.json --resume-from 249 --dry-run
```

Output:
```
RESUME DRY RUN - Run ID 249
===========================
Would skip successful jobs:
  ✓ download_data
  ✓ validate_data
  ✓ transform_part1

Would retry failed job:
  ✗ transform_part2

Would execute remaining jobs:
  - merge_results
  - generate_report
  - send_notification
  - cleanup

Total: 5 jobs to execute, 3 jobs to skip
```

### 5. Better Error Messages
When resume fails:
```
Error: Run ID 999 not found in history.

Recent runs for this config:
  Run 249 - FAILED  - 2025-05-23 09:45:00
  Run 248 - SUCCESS - 2025-05-23 09:00:00
  Run 247 - FAILED  - 2025-05-23 08:30:00

Use --list-runs to see all available runs.
```

### 6. Add Run Status to Database
Store additional metadata:
- Config file path/hash
- User who ran it
- Resume parent run ID (if resumed)
- Failure summary

## Implementation Priority

1. **High Priority**:
   - Add --list-runs command
   - Improve execution summary with resume instructions
   - Add --show-run command

2. **Medium Priority**:
   - Support --dry-run with --resume-from
   - Better error messages for invalid run IDs
   - Add run metadata to database

3. **Low Priority**:
   - Web UI for run history
   - Run comparison features
   - Automatic resume suggestions

## Benefits

1. **Discoverability**: Users can easily find and understand resume options
2. **Confidence**: Preview what will happen before resuming
3. **Debugging**: Better visibility into past runs and failures
4. **Automation**: Scripts can query run history programmatically
5. **User-Friendly**: Clear instructions at every step

## Database Changes Needed

Add table for run metadata:
```sql
CREATE TABLE run_metadata (
    run_id INTEGER PRIMARY KEY,
    config_path TEXT,
    config_hash TEXT,
    parent_run_id INTEGER,  -- If resumed from another run
    total_jobs INTEGER,
    completed_jobs INTEGER,
    failed_jobs INTEGER,
    skipped_jobs INTEGER,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds REAL,
    status TEXT,
    failure_summary TEXT
);
```

This would enable efficient querying of run history and better resume functionality.