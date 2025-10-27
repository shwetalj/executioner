/**
 * Input validation and sanitization utilities
 * Provides security-focused validation for user inputs
 */

/**
 * Validate and sanitize command strings
 * Checks for potentially dangerous patterns
 */
export function validateCommand(command) {
  if (!command || typeof command !== 'string') {
    return { valid: false, error: 'Command must be a non-empty string' };
  }

  // Check for dangerous command patterns
  const dangerousPatterns = [
    /rm\s+-rf\s+\//i,              // rm -rf /
    /dd\s+if=.*of=\/dev\//i,       // dd commands targeting system devices
    /mkfs\./i,                      // filesystem formatting
    /:\(\)\{.*\|.*&\};/,           // fork bomb pattern
    />\/dev\/sda/i,                // direct disk writes
    /chmod\s+777\s+\//i,           // dangerous permission changes
    /curl.*\|\s*sh/i,              // curl pipe to shell
    /wget.*\|\s*bash/i,            // wget pipe to bash
  ];

  for (const pattern of dangerousPatterns) {
    if (pattern.test(command)) {
      return { 
        valid: false, 
        error: 'Command contains potentially dangerous operations',
        warning: 'This command pattern has been blocked for security reasons'
      };
    }
  }

  // Warn about potentially risky but not blocked patterns
  const warningPatterns = [
    /sudo/i,
    /rm\s+-rf/i,
    /chmod/i,
    /chown/i,
    /\/etc\//,
    /\/sys\//,
    /\/proc\//,
  ];

  const warnings = [];
  for (const pattern of warningPatterns) {
    if (pattern.test(command)) {
      warnings.push('Command contains potentially risky operations');
      break;
    }
  }

  return { 
    valid: true, 
    sanitized: command.trim(),
    warnings 
  };
}

/**
 * Validate job ID format
 */
export function validateJobId(id) {
  if (!id || typeof id !== 'string') {
    return { valid: false, error: 'Job ID is required' };
  }

  // Allow alphanumeric, underscore, and hyphen
  const validIdPattern = /^[a-zA-Z0-9_-]+$/;
  if (!validIdPattern.test(id)) {
    return { 
      valid: false, 
      error: 'Job ID can only contain letters, numbers, underscores, and hyphens' 
    };
  }

  if (id.length > 100) {
    return { valid: false, error: 'Job ID must be less than 100 characters' };
  }

  return { valid: true, sanitized: id.trim() };
}

/**
 * Validate timeout value
 */
export function validateTimeout(timeout) {
  const num = Number(timeout);
  if (isNaN(num) || num < 0) {
    return { valid: false, error: 'Timeout must be a positive number' };
  }
  
  if (num > 86400) { // 24 hours
    return { 
      valid: false, 
      error: 'Timeout cannot exceed 24 hours (86400 seconds)' 
    };
  }

  return { valid: true, sanitized: num };
}

/**
 * Validate retry configuration
 */
export function validateRetryConfig(config) {
  const errors = [];
  
  if (config.max_retries !== undefined) {
    const retries = Number(config.max_retries);
    if (isNaN(retries) || retries < 0 || retries > 10) {
      errors.push('Max retries must be between 0 and 10');
    }
  }

  if (config.retry_delay !== undefined) {
    const delay = Number(config.retry_delay);
    if (isNaN(delay) || delay < 0 || delay > 3600) {
      errors.push('Retry delay must be between 0 and 3600 seconds');
    }
  }

  if (config.retry_backoff !== undefined) {
    const backoff = Number(config.retry_backoff);
    if (isNaN(backoff) || backoff < 1 || backoff > 5) {
      errors.push('Retry backoff must be between 1 and 5');
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate environment variables
 */
export function validateEnvVariables(envVars) {
  if (!envVars || typeof envVars !== 'object') {
    return { valid: true }; // env vars are optional
  }

  const errors = [];
  const warnings = [];

  for (const [key, value] of Object.entries(envVars)) {
    // Check key format
    if (!/^[A-Z_][A-Z0-9_]*$/i.test(key)) {
      errors.push(`Invalid environment variable name: ${key}`);
    }

    // Check for sensitive values that shouldn't be exposed
    const sensitiveKeys = ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE'];
    if (sensitiveKeys.some(sensitive => key.toUpperCase().includes(sensitive))) {
      warnings.push(`Environment variable '${key}' may contain sensitive data`);
    }

    // Validate value is a string
    if (typeof value !== 'string') {
      errors.push(`Environment variable '${key}' must have a string value`);
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * Validate email configuration
 */
export function validateEmailConfig(config) {
  const errors = [];

  if (config.email_address) {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(config.email_address)) {
      errors.push('Invalid email address format');
    }
  }

  if (config.smtp_server) {
    // Basic hostname validation
    const hostnamePattern = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9](?:\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9])*$/;
    if (!hostnamePattern.test(config.smtp_server)) {
      errors.push('Invalid SMTP server hostname');
    }
  }

  if (config.smtp_port !== undefined) {
    const port = Number(config.smtp_port);
    if (isNaN(port) || port < 1 || port > 65535) {
      errors.push('SMTP port must be between 1 and 65535');
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate complete job configuration
 */
export function validateJobConfig(job) {
  const errors = [];
  const warnings = [];

  // Validate required fields
  if (!job.id) {
    errors.push('Job ID is required');
  } else {
    const idValidation = validateJobId(job.id);
    if (!idValidation.valid) {
      errors.push(idValidation.error);
    }
  }

  if (!job.command) {
    errors.push('Job command is required');
  } else {
    const cmdValidation = validateCommand(job.command);
    if (!cmdValidation.valid) {
      errors.push(cmdValidation.error);
    } else if (cmdValidation.warnings?.length > 0) {
      warnings.push(...cmdValidation.warnings);
    }
  }

  // Validate optional fields
  if (job.timeout !== undefined) {
    const timeoutValidation = validateTimeout(job.timeout);
    if (!timeoutValidation.valid) {
      errors.push(timeoutValidation.error);
    }
  }

  if (job.max_retries !== undefined || job.retry_delay !== undefined || job.retry_backoff !== undefined) {
    const retryValidation = validateRetryConfig(job);
    if (!retryValidation.valid) {
      errors.push(...retryValidation.errors);
    }
  }

  if (job.env_variables) {
    const envValidation = validateEnvVariables(job.env_variables);
    if (!envValidation.valid) {
      errors.push(...envValidation.errors);
    }
    if (envValidation.warnings?.length > 0) {
      warnings.push(...envValidation.warnings);
    }
  }

  // Validate dependencies
  if (job.dependencies && Array.isArray(job.dependencies)) {
    for (const dep of job.dependencies) {
      const depValidation = validateJobId(dep);
      if (!depValidation.valid) {
        errors.push(`Invalid dependency ID '${dep}': ${depValidation.error}`);
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * Sanitize configuration for safe storage/display
 * Masks sensitive fields
 */
export function sanitizeConfigForDisplay(config) {
  const sanitized = JSON.parse(JSON.stringify(config)); // Deep clone

  // Mask sensitive fields
  if (sanitized.smtp_password) {
    sanitized.smtp_password = '********';
  }

  // Mask environment variables with sensitive names
  if (sanitized.env_variables) {
    const sensitiveKeys = ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE', 'API'];
    for (const key of Object.keys(sanitized.env_variables)) {
      if (sensitiveKeys.some(sensitive => key.toUpperCase().includes(sensitive))) {
        sanitized.env_variables[key] = '********';
      }
    }
  }

  // Mask job-level environment variables
  if (sanitized.jobs && Array.isArray(sanitized.jobs)) {
    for (const job of sanitized.jobs) {
      if (job.env_variables) {
        const sensitiveKeys = ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'PRIVATE', 'API'];
        for (const key of Object.keys(job.env_variables)) {
          if (sensitiveKeys.some(sensitive => key.toUpperCase().includes(sensitive))) {
            job.env_variables[key] = '********';
          }
        }
      }
    }
  }

  return sanitized;
}