# Executioner CLI Restructuring Proposal

## Current Issues

The current executioner CLI has several usability issues:

1. **Unclear dependencies between flags**: `--mark-success` requires `-r` and `-j` but this isn't clear from the usage line
2. **Mixed concerns**: Execution options are mixed with history/management operations
3. **Inconsistent patterns**: Some operations use flags (`--list-runs`) while others could be better as subcommands
4. **Limited extensibility**: Adding new operations clutters the main argument namespace

## Proposed Subcommand Structure

### Overview

Transform executioner from a single-command CLI to a multi-command structure similar to git, docker, or kubectl.

```
executioner <command> [options]
```

### Commands

#### 1. `run` (default command)
Execute jobs from a configuration file.

```bash
# Current syntax (still supported)
executioner -c config.json [options]

# New explicit syntax
executioner run -c config.json [options]
executioner run config.json [options]  # -c optional when using subcommand

# Options:
  -c, --config          Configuration file (default: jobs_config.json)
  --continue-on-error   Continue on job failures
  --dry-run            Show execution plan without running
  --skip JOB_ID        Skip specific jobs
  --env KEY=VALUE      Set environment variables
  --parallel           Enable parallel execution
  --workers N          Number of parallel workers
  --sequential         Force sequential execution
  --debug              Enable debug logging
  --verbose            Enable verbose logging
  --visible            Show environment variables
```

#### 2. `history` 
Manage and view execution history.

```bash
# List recent runs
executioner history list [--app APP_NAME] [--limit N] [--status STATUS]

# Show details for a specific run
executioner history show RUN_ID [--format json|table]

# Mark jobs as successful
executioner history mark-success RUN_ID JOB_ID1,JOB_ID2 [--reason TEXT]

# Delete old history
executioner history clean [--days N] [--keep-failed]

# Export history
executioner history export [--format csv|json] [--output FILE]
```

#### 3. `resume`
Resume a previous execution.

```bash
# Resume from a run
executioner resume RUN_ID [--failed-only] [--skip JOB_ID]

# Interactive resume
executioner resume RUN_ID --interactive
```

#### 4. `config`
Configuration file utilities.

```bash
# Show sample configuration
executioner config sample [--type basic|advanced|parallel]

# Validate configuration
executioner config validate CONFIG_FILE [--strict]

# Convert/upgrade configuration
executioner config upgrade OLD_CONFIG -o NEW_CONFIG

# Explain configuration
executioner config explain CONFIG_FILE [--job JOB_ID]
```

#### 5. `jobs`
Job inspection and debugging.

```bash
# List jobs in a config
executioner jobs list CONFIG_FILE [--deps] [--tree]

# Show job details
executioner jobs show CONFIG_FILE JOB_ID

# Validate job dependencies
executioner jobs check-deps CONFIG_FILE

# Generate dependency graph
executioner jobs graph CONFIG_FILE [--format dot|mermaid] [-o FILE]
```

#### 6. `debug`
Debug and troubleshooting utilities.

```bash
# Test a single job
executioner debug run CONFIG_FILE JOB_ID [--env KEY=VALUE]

# Check environment
executioner debug env CONFIG_FILE [--job JOB_ID]

# Validate commands
executioner debug check-commands CONFIG_FILE

# Show system info
executioner debug info
```

### Global Options

These options work with all commands:

```bash
--help, -h       Show help
--version        Show version
--quiet, -q      Suppress output
--no-color       Disable colored output
--log-level      Set log level (debug|info|warning|error)
--log-file       Write logs to file
```

## Implementation Plan

### Phase 1: Core Structure
1. Implement subcommand parser using argparse subparsers
2. Move existing functionality to appropriate subcommands
3. Maintain backward compatibility with deprecation warnings

### Phase 2: Enhanced Features
1. Add new history management features
2. Implement config validation and explanation
3. Add job debugging capabilities

### Phase 3: Polish
1. Improve help text and examples
2. Add shell completion support
3. Create migration guide

## Backward Compatibility

To ensure smooth transition:

1. **Default behavior**: When no subcommand is provided, assume `run` command
2. **Flag mapping**: Old flags continue to work with deprecation warnings
3. **Grace period**: Support both syntaxes for 6 months
4. **Clear messaging**: Deprecation warnings show the new syntax

### Examples of backward compatibility:

```bash
# Old syntax (deprecated but still works)
executioner --list-runs
# Shows: "DEPRECATED: Use 'executioner history list' instead"

# Old syntax
executioner --mark-success -r 123 -j job1,job2
# Shows: "DEPRECATED: Use 'executioner history mark-success 123 job1,job2' instead"

# Old syntax for main execution still works
executioner -c config.json --dry-run
# No deprecation (this is still valid as shorthand for 'executioner run')
```

## Benefits

1. **Clarity**: Each command has a clear purpose
2. **Discoverability**: `executioner --help` shows available commands
3. **Extensibility**: Easy to add new commands without cluttering
4. **Best practices**: Follows CLI patterns from popular tools
5. **Better help**: Each subcommand can have detailed help
6. **Logical grouping**: Related operations are grouped together

## Migration Examples

### Before
```bash
executioner -c jobs.json --dry-run
executioner --list-runs myapp
executioner --show-run 123
executioner --mark-success -r 123 -j job1,job2
executioner --sample-config
```

### After
```bash
executioner run jobs.json --dry-run
executioner history list --app myapp
executioner history show 123
executioner history mark-success 123 job1,job2
executioner config sample
```

## Future Extensions

With subcommand structure, we can easily add:

```bash
# Plugin management
executioner plugin list
executioner plugin install PLUGIN_NAME

# Remote execution (future)
executioner remote add SERVER_NAME URL
executioner remote run SERVER_NAME CONFIG_FILE

# Workflow management
executioner workflow create
executioner workflow edit WORKFLOW_ID

# Monitoring
executioner monitor start CONFIG_FILE
executioner monitor status
```