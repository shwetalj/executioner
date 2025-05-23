# SQL Injection Fix Documentation

## Problem
The JobHistoryManager class had a SQL injection vulnerability where column names were directly interpolated into ALTER TABLE statements without validation:

```python
# VULNERABLE CODE:
alter_sql = f"ALTER TABLE job_history ADD COLUMN {col_name} {col_type} {col_constraint}".strip()
cursor.execute(alter_sql)
```

## Solution Implemented
1. **Added a whitelist of allowed columns** as a class constant:
   ```python
   ALLOWED_COLUMNS = {
       'retry_history': ('TEXT', ''),
       'last_exit_code': ('INTEGER', ''),
       'retry_count': ('INTEGER', 'DEFAULT 0'),
       'last_error': ('TEXT', ''),
       'duration_seconds': ('REAL', ''),
       'memory_usage_mb': ('REAL', ''),
       'cpu_usage_percent': ('REAL', '')
   }
   ```

2. **Validated all column names against the whitelist** before using them in SQL:
   ```python
   if col_name not in self.ALLOWED_COLUMNS:
       self.logger.error(f"Attempted to add non-whitelisted column: {col_name}")
       continue
   ```

3. **Fixed both occurrences** in:
   - `update_retry_history()` method (line 90)
   - `get_last_exit_code()` method (line 169)

## Why This Works
- SQLite doesn't support parameterized queries for DDL statements (ALTER TABLE)
- A whitelist approach ensures only known, safe column names are used
- Any attempt to inject malicious SQL through column names will be rejected
- The column types and constraints are also controlled through the whitelist

## Testing
The fix was tested with:
- Valid whitelisted columns (works correctly)
- Malicious column names (rejected)
- Normal operation of retry history tracking (unaffected)

## Files Modified
- `/home/sjoshi/claudelab/executioner/jobs/job_history_manager.py`

## Additional Recommendations
1. Consider moving the schema management to a dedicated module
2. Add unit tests for the whitelist validation
3. Review other dynamic SQL construction in the codebase
4. Consider using an ORM like SQLAlchemy for better SQL safety