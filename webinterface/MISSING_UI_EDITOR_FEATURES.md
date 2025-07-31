# Missing UI Editor Features

This document outlines the features that are currently missing from the Executioner Workflow Editor web interface.

## 1. Job Configuration Completeness

### Currently Missing Fields:
- **Environment Variables**: No UI to add/edit job-specific environment variables
- **Pre-checks**: Cannot configure pre-execution checks like `check_file_exists`
- **Post-checks**: Cannot configure post-execution checks like `check_no_ora_errors`
- **Retry Configuration**:
  - `max_retries`
  - `retry_delay`
  - `retry_backoff`
  - `retry_jitter`
  - `max_retry_time`
  - `retry_on_status`
  - `retry_on_exit_codes`
- **Shell Settings**:
  - `allow_shell`
  - `inherit_shell_env`

## 2. File Operations

### Missing Features:
- **Backend Integration**: Currently uses browser file API, no server persistence
- **Save As**: No way to save with a different filename
- **Recent Files**: No list of recently opened configurations
- **Auto-save**: No automatic saving of work
- **Cloud Storage**: No integration with cloud storage services

## 3. Workflow Execution & Monitoring

### Missing Features:
- **Run Workflow**: No button to execute the workflow via executioner.py
- **Job Status Visualization**: No way to see running/completed/failed jobs
- **Execution History**: No viewer for past execution runs
- **Real-time Monitoring**: No live updates of job progress
- **Log Viewer**: No integrated log viewing
- **Execution Controls**: No pause/resume/cancel functionality

## 4. Advanced Canvas Features

### Missing Features:
- **Copy/Paste**: Cannot duplicate jobs or selections
- **Multi-select**: Cannot select multiple nodes at once
- **Keyboard Navigation**: No arrow key movement between nodes
- **Zoom Level Indicator**: No display of current zoom percentage
- **Minimap**: No overview for large workflows
- **Snap-to-Grid**: No grid alignment option
- **Group/Ungroup**: Cannot group related jobs
- **Layers**: No layer management for complex workflows
- **Connection Routing**: No manual control over connection paths

## 5. Validation & Safety

### Missing Features:
- **Circular Dependency Detection**: No warning for circular dependencies
- **Job ID Validation**: No check for duplicate or invalid IDs
- **Command Validation**: No syntax checking for commands
- **Path Validation**: No verification of file paths
- **Unsaved Changes Warning**: No prompt when closing with modifications
- **Configuration Validation**: No overall config validation before save

## 6. User Experience Enhancements

### Missing Features:
- **Tooltips**: No helpful hover text on buttons/fields
- **Help Documentation**: No integrated help system
- **Search/Filter**: Cannot search jobs in sidebar
- **Job Templates**: No preset job configurations
- **Keyboard Shortcuts Guide**: No display of available shortcuts
- **Status Bar**: No information bar for current operations
- **Breadcrumbs**: No navigation path display
- **Customizable UI**: No way to hide/show panels

## 7. Import/Export Capabilities

### Missing Features:
- **Export as Image**: Cannot save workflow as PNG/SVG
- **Export as PDF**: No PDF generation
- **Import from CLI**: Cannot import existing executioner runs
- **Configuration Diff**: No way to compare two configurations
- **Batch Operations**: No bulk import/export
- **Format Conversion**: No conversion between config formats

## 8. Collaboration Features

### Missing Features:
- **Comments**: No way to add notes to jobs or workflow
- **Version Control**: No built-in versioning
- **Sharing**: No way to share configurations with others
- **Collaborative Editing**: No multi-user support
- **Change Tracking**: No audit trail of modifications

## 9. Advanced Application Configuration

### Missing Features:
- **Environment Variable Editor**: Complex UI for global env vars
- **SMTP Configuration Tester**: No way to test email settings
- **Plugin Management**: No UI for dependency_plugins
- **Security Policy Editor**: No advanced security settings

## 10. Performance & Scalability

### Missing Features:
- **Large Workflow Optimization**: Performance issues with 100+ jobs
- **Lazy Loading**: No progressive loading of large configs
- **Virtualization**: No virtual scrolling for job lists
- **Caching**: No client-side caching strategy

## Priority Recommendations

### High Priority:
1. Complete job configuration fields (env vars, checks, retry)
2. Add validation for circular dependencies and IDs
3. Implement unsaved changes warning
4. Add execution integration with backend

### Medium Priority:
1. Add copy/paste functionality
2. Implement search/filter for jobs
3. Add keyboard navigation
4. Create help tooltips

### Low Priority:
1. Export as image/PDF
2. Minimap for large workflows
3. Collaboration features
4. Advanced theming options

## Implementation Notes

- Consider using a state management library (Vuex/Pinia) for complex state
- Backend API needed for file operations and execution
- WebSocket connection recommended for real-time execution monitoring
- Consider adding unit tests for critical functionality