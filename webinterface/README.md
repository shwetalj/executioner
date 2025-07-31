# Executioner Workflow Editor

## Running the Application

The application requires a local web server to run properly because it uses Vue Single File Components (SFCs).

### Option 1: Using Python (Recommended)
```bash
# Navigate to the webinterface directory
cd /home/sjoshi/claudelab/executioner/webinterface

# Start a simple HTTP server
python3 -m http.server 8080

# Open in browser: http://localhost:8080
```

### Option 2: Using Node.js
```bash
# If you have Node.js installed
npx http-server -p 8080

# Open in browser: http://localhost:8080
```

### Option 3: Using the Standalone Version
If you can't run a web server, use the standalone version:
```bash
# Open index-standalone.html directly in your browser
```

## Files
- `index.html` - Main entry point (requires web server)
- `index-standalone.html` - Standalone version (can open directly)
- `App.vue` - Main application component
- `components/` - Vue components directory
  - `WorkflowCanvas.vue` - Visual DAG editor
  - `JobEditor.vue` - Job configuration editor
  - `JsonEditor.vue` - JSON configuration editor
  - `ApplicationConfig.vue` - Application-level settings editor