# Executioner Architecture Documentation

## Overview

The Executioner is a sophisticated job execution engine with dependency management, built using a modular, single-responsibility architecture. This document provides comprehensive diagrams and explanations of the system's components and execution flows.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Component Interactions](#component-interactions)
3. [Execution Flow](#execution-flow)
4. [Job Lifecycle](#job-lifecycle)
5. [Database Schema](#database-schema)
6. [Configuration Flow](#configuration-flow)

---

## System Architecture

### High-Level Component Overview

```mermaid
graph TB
    subgraph "CLI Layer"
        CLI[executioner.py<br/>CLI Entry Point]
    end
    
    subgraph "Core Orchestration"
        JE[JobExecutioner<br/>Main Coordinator]
        EO[ExecutionOrchestrator<br/>Flow Control]
    end
    
    subgraph "State Management"
        QM[QueueManager<br/>Job Queuing]
        SM[StateManager<br/>Run Lifecycle]
        EHM[ExecutionHistoryManager<br/>Persistence]
    end
    
    subgraph "Job Processing"
        JR[JobRunner<br/>Individual Execution]
        DM[DependencyManager<br/>Dependencies]
        CR[CheckRunner<br/>Validations]
    end
    
    subgraph "Support Systems"
        NM[NotificationManager<br/>Alerts]
        SR[SummaryReporter<br/>Output Display]
        LS[LoggingSetup<br/>Logging Config]
    end
    
    subgraph "Configuration"
        CL[Config Loader<br/>JSON Processing]
        CV[Config Validator<br/>Schema Validation]
    end
    
    subgraph "Database"
        SC[SQLite Connection<br/>Database Access]
        DB[(SQLite Database<br/>Job History & Runs)]
    end
    
    CLI --> JE
    JE --> EO
    JE --> QM
    JE --> SM
    JE --> SR
    EO --> JR
    QM --> DM
    SM --> EHM
    JR --> CR
    JE --> NM
    EHM --> SC
    SC --> DB
    JE --> CL
    CL --> CV
    
    style CLI fill:#e1f5fe
    style JE fill:#f3e5f5
    style EO fill:#e8f5e8
    style QM fill:#fff3e0
    style SM fill:#fff3e0
    style JR fill:#e8f5e8
    style DB fill:#ffebee
```

### Component Relationships

```mermaid
graph LR
    subgraph "Execution Control"
        JE[JobExecutioner]
        EO[ExecutionOrchestrator]
        JE --> EO
    end
    
    subgraph "Job Management"
        QM[QueueManager]
        JR[JobRunner]
        DM[DependencyManager]
        QM --> JR
        QM --> DM
    end
    
    subgraph "State & History"
        SM[StateManager]
        EHM[ExecutionHistoryManager]
        SM --> EHM
    end
    
    subgraph "Reporting"
        SR[SummaryReporter]
        NM[NotificationManager]
    end
    
    JE --> QM
    JE --> SM
    JE --> SR
    JE --> NM
    EO --> QM
    EO --> SM
    
    style JE fill:#f3e5f5
    style EO fill:#e8f5e8
    style QM fill:#fff3e0
    style JR fill:#e8f5e8
    style SM fill:#fff3e0
```

---

## Component Interactions

### Data Flow Between Components

```mermaid
sequenceDiagram
    participant CLI as executioner.py
    participant JE as JobExecutioner
    participant EO as ExecutionOrchestrator
    participant QM as QueueManager
    participant SM as StateManager
    participant JR as JobRunner
    participant EHM as ExecutionHistoryManager
    participant DB as SQLite Database
    
    CLI->>JE: Initialize with config
    JE->>SM: Initialize state & get run ID
    SM->>EHM: Get new run ID
    EHM->>DB: Query max run ID
    DB-->>EHM: Return max ID
    EHM-->>SM: Return new run ID
    
    JE->>QM: Initialize job queue
    QM->>QM: Queue initial jobs
    
    JE->>EO: Start execution
    EO->>QM: Get next job
    QM-->>EO: Return job ID
    
    EO->>JR: Execute job
    JR->>JR: Run command & monitor
    JR-->>EO: Return result
    
    EO->>QM: Mark job complete
    QM->>QM: Queue dependent jobs
    
    EO->>SM: Update execution state
    SM->>EHM: Record job status
    EHM->>DB: Persist to database
```

---

## Execution Flow

### Main Execution Process

```mermaid
flowchart TD
    Start([Start]) --> LoadConfig[Load Configuration]
    LoadConfig --> Validate[Validate Config]
    Validate --> InitComponents[Initialize Components]
    
    InitComponents --> GetRunID[Get New Run ID]
    GetRunID --> SetupLogging[Setup Logging]
    SetupLogging --> CheckDeps{Check Dependencies}
    
    CheckDeps -->|Circular Deps| AbortCircular[Abort: Circular Dependencies]
    CheckDeps -->|Missing Deps| AbortMissing[Abort: Missing Dependencies]
    CheckDeps -->|Valid| IsDryRun{Dry Run Mode?}
    
    IsDryRun -->|Yes| DisplayPlan[Display Execution Plan]
    DisplayPlan --> ExitDry[Exit with Plan]
    
    IsDryRun -->|No| QueueJobs[Queue Initial Jobs]
    QueueJobs --> SetupHandler[Setup Interrupt Handler]
    SetupHandler --> IsParallel{Parallel Mode?}
    
    IsParallel -->|Yes| ParallelExec[Parallel Execution<br/>ThreadPoolExecutor]
    IsParallel -->|No| SequentialExec[Sequential Execution<br/>Queue Processing]
    
    ParallelExec --> Monitor[Monitor Job Progress]
    SequentialExec --> Monitor
    
    Monitor --> AllComplete{All Jobs Complete?}
    AllComplete -->|No| GetNext[Get Next Job]
    GetNext --> ExecuteJob[Execute Job]
    ExecuteJob --> UpdateStatus[Update Job Status]
    UpdateStatus --> QueueDeps[Queue Dependent Jobs]
    QueueDeps --> AllComplete
    
    AllComplete -->|Yes| Cleanup[Cleanup Resources]
    Cleanup --> GenerateSummary[Generate Summary]
    GenerateSummary --> SendNotifications[Send Notifications]
    SendNotifications --> End([End])
    
    AbortCircular --> End
    AbortMissing --> End
    ExitDry --> End
    
    style Start fill:#e8f5e8
    style End fill:#ffebee
    style AbortCircular fill:#ffcdd2
    style AbortMissing fill:#ffcdd2
    style IsDryRun fill:#fff3e0
    style IsParallel fill:#fff3e0
    style AllComplete fill:#fff3e0
```

### Decision Points & Flow Control

```mermaid
graph TD
    subgraph "Pre-Execution Validation"
        A[Start] --> B[Load Config]
        B --> C{Valid Config?}
        C -->|No| D[Exit with Error]
        C -->|Yes| E{Circular Dependencies?}
        E -->|Yes| F[Exit with Error]
        E -->|No| G{Missing Dependencies?}
        G -->|Yes| H[Exit with Error]
    end
    
    subgraph "Execution Mode Selection"
        G -->|No| I{Dry Run?}
        I -->|Yes| J[Display Plan & Exit]
        I -->|No| K{Parallel Mode?}
        K -->|Yes| L[Parallel Execution]
        K -->|No| M[Sequential Execution]
    end
    
    subgraph "Job Processing Loop"
        L --> N{Jobs Remaining?}
        M --> N
        N -->|Yes| O[Execute Next Job]
        O --> P{Job Success?}
        P -->|Yes| Q[Queue Dependent Jobs]
        P -->|No| R[Handle Failure]
        Q --> N
        R --> S{Continue on Error?}
        S -->|Yes| N
        S -->|No| T[Abort Execution]
    end
    
    subgraph "Completion"
        N -->|No| U[Generate Summary]
        T --> U
        U --> V[Send Notifications]
        V --> W[End]
    end
    
    style D fill:#ffcdd2
    style F fill:#ffcdd2
    style H fill:#ffcdd2
    style T fill:#ffcdd2
```

---

## Job Lifecycle

### Individual Job Processing

```mermaid
stateDiagram-v2
    [*] --> Pending: Job Created
    
    Pending --> Queued: Dependencies Met
    Pending --> Blocked: Dependencies Not Met
    
    Blocked --> Queued: Dependencies Resolved
    Blocked --> Skipped: Dependency Failed
    
    Queued --> Running: Job Started
    
    Running --> PreChecks: Execute Pre-checks
    PreChecks --> PreCheckFailed: Pre-check Failed
    PreChecks --> Executing: Pre-checks Passed
    
    Executing --> PostChecks: Command Completed
    Executing --> Failed: Command Failed
    Executing --> Timeout: Timeout Reached
    
    PostChecks --> Success: Post-checks Passed
    PostChecks --> PostCheckFailed: Post-check Failed
    
    Failed --> Retrying: Retry Conditions Met
    Timeout --> Retrying: Retry Conditions Met
    PreCheckFailed --> Retrying: Retry Conditions Met
    PostCheckFailed --> Retrying: Retry Conditions Met
    
    Retrying --> Running: Retry Attempt
    Retrying --> Failed: Max Retries Exceeded
    
    Success --> [*]: Job Complete
    Failed --> [*]: Job Complete
    Skipped --> [*]: Job Complete
    
    note right of Success: Dependent jobs queued
    note right of Failed: May block dependents
    note right of Skipped: Dependents may be skipped
```

### Job Execution Detail Flow

```mermaid
flowchart TD
    Start([Job Start]) --> Setup[Setup Job Environment]
    Setup --> PreCheck{Pre-checks<br/>Required?}
    
    PreCheck -->|Yes| RunPreCheck[Execute Pre-checks]
    PreCheck -->|No| RunCommand[Execute Command]
    
    RunPreCheck --> PreCheckResult{Pre-checks<br/>Pass?}
    PreCheckResult -->|No| PreCheckFail[Mark Pre-check Failed]
    PreCheckResult -->|Yes| RunCommand
    
    RunCommand --> Monitor[Monitor Execution]
    Monitor --> CommandResult{Command<br/>Success?}
    
    CommandResult -->|Timeout| TimeoutHandle[Handle Timeout]
    CommandResult -->|Error| ErrorHandle[Handle Error]
    CommandResult -->|Success| PostCheck{Post-checks<br/>Required?}
    
    PostCheck -->|No| Success[Mark Success]
    PostCheck -->|Yes| RunPostCheck[Execute Post-checks]
    
    RunPostCheck --> PostCheckResult{Post-checks<br/>Pass?}
    PostCheckResult -->|No| PostCheckFail[Mark Post-check Failed]
    PostCheckResult -->|Yes| Success
    
    TimeoutHandle --> RetryCheck{Retry<br/>Available?}
    ErrorHandle --> RetryCheck
    PreCheckFail --> RetryCheck
    PostCheckFail --> RetryCheck
    
    RetryCheck -->|Yes| Delay[Wait Retry Delay]
    RetryCheck -->|No| Failed[Mark Failed]
    
    Delay --> RunCommand
    
    Success --> QueueDeps[Queue Dependent Jobs]
    Failed --> End([Job End])
    QueueDeps --> End
    
    style Success fill:#c8e6c9
    style Failed fill:#ffcdd2
    style TimeoutHandle fill:#fff3e0
    style ErrorHandle fill:#fff3e0
```

---

## Database Schema

### Table Relationships

```mermaid
erDiagram
    RUN_SUMMARY {
        INTEGER run_id PK
        TEXT application_name
        TEXT start_time
        TEXT end_time
        TEXT status
        INTEGER total_jobs
        INTEGER completed_jobs
        INTEGER failed_jobs
        INTEGER skipped_jobs
        INTEGER exit_code
    }
    
    JOB_HISTORY {
        INTEGER id PK
        TEXT run_id FK
        TEXT application_name
        TEXT job_id
        TEXT status
        TEXT start_time
        TEXT end_time
        TEXT command
        TEXT exit_code
        TEXT retry_count
        TEXT log_file
    }
    
    RETRY_HISTORY {
        INTEGER id PK
        TEXT run_id FK
        TEXT job_id FK
        TEXT attempt_number
        TEXT timestamp
        TEXT duration
        TEXT success
        TEXT exit_code
        TEXT status
    }
    
    RUN_SUMMARY ||--o{ JOB_HISTORY : "has jobs"
    RUN_SUMMARY ||--o{ RETRY_HISTORY : "has retries"
    JOB_HISTORY ||--o{ RETRY_HISTORY : "has retry attempts"
```

### Data Flow in Database Operations

```mermaid
sequenceDiagram
    participant EO as ExecutionOrchestrator
    participant SM as StateManager
    participant EHM as ExecutionHistoryManager
    participant SC as SQLiteConnection
    participant DB as Database
    
    Note over EO,DB: Run Initialization
    EO->>SM: start_execution()
    SM->>EHM: get_new_run_id()
    EHM->>SC: db_connection()
    SC->>DB: SELECT MAX(run_id)
    DB-->>SC: Return max ID
    SC-->>EHM: Connection closed
    EHM-->>SM: Return new run_id
    
    SM->>EHM: create_run_summary()
    EHM->>SC: db_connection()
    SC->>DB: INSERT INTO run_summary
    SC-->>EHM: Connection closed
    
    Note over EO,DB: Job Execution
    EO->>EHM: update_job_status()
    EHM->>SC: db_connection()
    SC->>DB: INSERT INTO job_history
    SC-->>EHM: Connection closed
    
    Note over EO,DB: Run Completion
    SM->>EHM: update_run_summary()
    EHM->>SC: db_connection()
    SC->>DB: UPDATE run_summary
    SC-->>EHM: Connection closed
```

---

## Configuration Flow

### Configuration Loading and Validation

```mermaid
flowchart TD
    Start([Configuration Start]) --> ReadFile[Read JSON Config File]
    ReadFile --> ParseJSON{Valid JSON?}
    
    ParseJSON -->|No| JSONError[JSON Parse Error]
    ParseJSON -->|Yes| ValidateSchema[Validate Schema]
    
    ValidateSchema --> CheckRequired{Required Fields<br/>Present?}
    CheckRequired -->|No| RequiredError[Missing Required Fields]
    CheckRequired -->|Yes| ValidateJobs[Validate Jobs Array]
    
    ValidateJobs --> JobLoop{For Each Job}
    JobLoop --> CheckJobID{Job ID<br/>Present?}
    CheckJobID -->|No| JobIDError[Missing Job ID]
    CheckJobID -->|Yes| CheckCommand{Command<br/>Present?}
    
    CheckCommand -->|No| CommandError[Missing Command]
    CheckCommand -->|Yes| ValidateDeps[Validate Dependencies]
    
    ValidateDeps --> DepsExist{Dependencies<br/>Exist?}
    DepsExist -->|No| DepsError[Invalid Dependencies]
    DepsExist -->|Yes| NextJob{More Jobs?}
    
    NextJob -->|Yes| JobLoop
    NextJob -->|No| CheckCircular[Check Circular Dependencies]
    
    CheckCircular --> Circular{Circular<br/>Dependencies?}
    Circular -->|Yes| CircularError[Circular Dependency Error]
    Circular -->|No| ConfigValid[Configuration Valid]
    
    JSONError --> ConfigError[Configuration Error]
    RequiredError --> ConfigError
    JobIDError --> ConfigError
    CommandError --> ConfigError
    DepsError --> ConfigError
    CircularError --> ConfigError
    
    ConfigValid --> Success([Configuration Success])
    ConfigError --> Failure([Configuration Failure])
    
    style Success fill:#c8e6c9
    style Failure fill:#ffcdd2
    style ConfigError fill:#ffcdd2
```

### Configuration Structure

```mermaid
graph TB
    subgraph "Root Configuration"
        Config[JSON Config File]
        Config --> AppName[application_name]
        Config --> Jobs[jobs[]]
        Config --> Settings[Global Settings]
    end
    
    subgraph "Global Settings"
        Settings --> Parallel[parallel: bool]
        Settings --> MaxWorkers[max_workers: int]
        Settings --> Timeout[default_timeout: int]
        Settings --> Email[email_settings{}]
        Settings --> Env[env_variables{}]
    end
    
    subgraph "Job Configuration"
        Jobs --> Job1[Job Object]
        Job1 --> JobID[id: string]
        Job1 --> JobCmd[command: string]
        Job1 --> JobDeps[dependencies: array]
        Job1 --> JobEnv[env_variables: object]
        Job1 --> JobTimeout[timeout: int]
        Job1 --> JobRetry[retry_settings: object]
        Job1 --> JobChecks[pre/post_checks: array]
    end
    
    subgraph "Validation Rules"
        Rules[Validation Rules]
        Rules --> UniqueIDs[Unique Job IDs]
        Rules --> ValidDeps[Valid Dependencies]
        Rules --> NoCircular[No Circular Dependencies]
        Rules --> ValidCommands[Non-empty Commands]
    end
    
    style Config fill:#e1f5fe
    style Settings fill:#f3e5f5
    style Jobs fill:#e8f5e8
    style Rules fill:#fff3e0
```

---

## Summary

The Executioner architecture follows these key principles:

1. **Single Responsibility**: Each component has a focused, well-defined purpose
2. **Separation of Concerns**: Clear boundaries between configuration, execution, state management, and reporting
3. **Dependency Injection**: Components receive their dependencies, making testing easier
4. **Database Abstraction**: SQLite-specific implementation can be easily extended to other databases
5. **Modular Design**: Components can be independently tested and maintained

### Key Benefits

- **Maintainability**: Clear component boundaries make changes easier
- **Testability**: Each component can be unit tested in isolation
- **Extensibility**: New databases, notification methods, or execution strategies can be added easily
- **Reliability**: Robust error handling and state management
- **Scalability**: Parallel execution and efficient resource management

### Future Extensions

The architecture supports easy addition of:
- New database backends (PostgreSQL, MySQL)
- Additional notification channels (Slack, Teams, webhooks)
- Different execution strategies (distributed execution)
- Enhanced monitoring and metrics
- Configuration templating and inheritance