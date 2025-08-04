# Environment Variable Isolation Feature

## Overview

The executioner now supports controlling which environment variables are inherited from the parent shell. This provides better security, reproducibility, and explicit dependency management.

## Configuration Options

The `inherit_shell_env` setting in your configuration file controls environment inheritance:

### 1. Full Inheritance (Default - Backward Compatible)
```json
{
  "inherit_shell_env": true,
  // OR omit the setting entirely
}
```
All environment variables from the parent shell are inherited.

### 2. Complete Isolation
```json
{
  "inherit_shell_env": false
}
```
No environment variables from the parent shell are inherited. Only variables defined in the config or via CLI are available.

### 3. Default Whitelist
```json
{
  "inherit_shell_env": "default"
}
```
Only commonly needed system variables are inherited:
- System paths: `PATH`, `LD_LIBRARY_PATH`
- User info: `HOME`, `USER`, `SHELL`, `HOSTNAME`
- Terminal: `TERM`, `DISPLAY`
- Locale: `LANG`, `LC_ALL`, `LC_CTYPE`
- Timezone: `TZ`
- Temp dirs: `TMPDIR`, `TEMP`, `TMP`
- Common tools: `JAVA_HOME`, `PYTHON_HOME`, `NODE_PATH`

### 4. Custom Whitelist
```json
{
  "inherit_shell_env": ["PATH", "HOME", "MY_CUSTOM_VAR"]
}
```
Only the specified environment variables are inherited.

## Examples

### Example 1: Isolated Build Environment
```json
{
  "application_name": "secure_build",
  "inherit_shell_env": false,
  "env_variables": {
    "BUILD_DIR": "/opt/build",
    "VERSION": "1.0.0"
  },
  "jobs": [
    {
      "id": "compile",
      "command": "make all",
      "env_variables": {
        "CC": "gcc",
        "CFLAGS": "-O2"
      }
    }
  ]
}
```

### Example 2: Development Environment with Tools
```json
{
  "application_name": "dev_env",
  "inherit_shell_env": "default",
  "env_variables": {
    "PROJECT_ROOT": "${HOME}/myproject"
  }
}
```

### Example 3: Custom Environment for Database Scripts
```json
{
  "application_name": "db_scripts",
  "inherit_shell_env": ["PATH", "HOME", "ORACLE_HOME", "TNS_ADMIN"],
  "env_variables": {
    "DB_USER": "myapp",
    "DB_SCHEMA": "production"
  }
}
```

## Benefits

1. **Security**: Sensitive environment variables (AWS keys, passwords) won't leak into jobs unless explicitly needed
2. **Reproducibility**: Jobs run the same way regardless of user's shell environment
3. **Debugging**: Fewer variables to consider when troubleshooting
4. **Documentation**: The config file explicitly shows what external dependencies are needed