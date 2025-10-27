/**
 * Centralized error handling and notification system
 */

// Store for notifications (in production, this would integrate with a UI notification system)
let notificationCallback = null;

/**
 * Set the notification callback function
 */
export function setNotificationHandler(callback) {
  notificationCallback = callback;
}

/**
 * Show a notification to the user
 */
export function showNotification(message, type = 'info', duration = 5000) {
  const notification = {
    id: Date.now() + Math.random(),
    message,
    type, // 'success', 'error', 'warning', 'info'
    duration,
    timestamp: new Date()
  };

  if (notificationCallback) {
    notificationCallback(notification);
  }

  // Also log to console based on type
  switch (type) {
    case 'error':
      console.error(`[ERROR] ${message}`);
      break;
    case 'warning':
      console.warn(`[WARNING] ${message}`);
      break;
    case 'success':
      console.log(`[SUCCESS] ${message}`);
      break;
    default:
      console.info(`[INFO] ${message}`);
  }

  return notification;
}

/**
 * Handle different types of errors with appropriate user feedback
 */
export function handleError(error, context = '') {
  console.error(`Error in ${context}:`, error);

  // Map error codes to user-friendly messages
  const errorMessages = {
    'DUPLICATE_JOB_ID': 'A job with this ID already exists. Please use a unique ID.',
    'CIRCULAR_DEPENDENCY': 'This connection would create a circular dependency. Jobs cannot depend on themselves directly or indirectly.',
    'INVALID_JSON': 'The JSON configuration is invalid. Please check the syntax.',
    'NETWORK_ERROR': 'Network error. Please check your connection and try again.',
    'VALIDATION_ERROR': 'Validation failed. Please check your input.',
    'FILE_READ_ERROR': 'Failed to read the file. Please check if the file exists and is accessible.',
    'FILE_WRITE_ERROR': 'Failed to save the file. Please check permissions.',
    'COMMAND_DANGEROUS': 'The command contains potentially dangerous operations and has been blocked.',
    'MISSING_DEPENDENCY': 'The job depends on a non-existent job. Please check dependencies.',
    'TIMEOUT_EXCEEDED': 'Operation timed out. Please try again.',
    'MAX_RETRIES_EXCEEDED': 'Maximum retry attempts exceeded.',
    'INVALID_CONFIG': 'The configuration is invalid. Please check all required fields.',
    'PERMISSION_DENIED': 'Permission denied. Please check your access rights.',
  };

  // Determine the error message and type
  let message = 'An unexpected error occurred';
  let type = 'error';

  if (error.code && errorMessages[error.code]) {
    message = errorMessages[error.code];
  } else if (error.message) {
    message = error.message;
  } else if (typeof error === 'string') {
    message = error;
  }

  // Add context if provided
  if (context) {
    message = `${context}: ${message}`;
  }

  // Show notification
  showNotification(message, type);

  // Return structured error info
  return {
    code: error.code || 'UNKNOWN_ERROR',
    message,
    context,
    timestamp: new Date(),
    originalError: error
  };
}

/**
 * Handle validation errors specifically
 */
export function handleValidationError(errors, warnings = []) {
  if (!errors || errors.length === 0) {
    if (warnings && warnings.length > 0) {
      warnings.forEach(warning => {
        showNotification(warning, 'warning');
      });
    }
    return null;
  }

  // Show each error as a notification
  errors.forEach(error => {
    showNotification(error, 'error');
  });

  // Also show warnings if any
  warnings.forEach(warning => {
    showNotification(warning, 'warning');
  });

  return {
    code: 'VALIDATION_ERROR',
    errors,
    warnings,
    timestamp: new Date()
  };
}

/**
 * Wrap async operations with error handling
 */
export async function withErrorHandling(operation, context = '') {
  try {
    return await operation();
  } catch (error) {
    handleError(error, context);
    throw error; // Re-throw to allow caller to handle if needed
  }
}

/**
 * Create a debounced error handler for frequent operations
 */
export function createDebouncedErrorHandler(delay = 1000) {
  let timeoutId = null;
  let pendingErrors = [];

  return {
    handleError(error, context) {
      pendingErrors.push({ error, context });

      if (timeoutId) {
        clearTimeout(timeoutId);
      }

      timeoutId = setTimeout(() => {
        if (pendingErrors.length === 1) {
          handleError(pendingErrors[0].error, pendingErrors[0].context);
        } else {
          showNotification(
            `${pendingErrors.length} errors occurred. Check console for details.`,
            'error'
          );
          pendingErrors.forEach(({ error, context }) => {
            console.error(`Error in ${context}:`, error);
          });
        }
        pendingErrors = [];
        timeoutId = null;
      }, delay);
    },

    clear() {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      pendingErrors = [];
    }
  };
}

/**
 * Error boundary for component operations
 */
export function createErrorBoundary(componentName) {
  return {
    wrap(fn) {
      return async function(...args) {
        try {
          return await fn.apply(this, args);
        } catch (error) {
          handleError(error, componentName);
          // Don't re-throw to prevent component crash
          return null;
        }
      };
    },

    wrapSync(fn) {
      return function(...args) {
        try {
          return fn.apply(this, args);
        } catch (error) {
          handleError(error, componentName);
          // Don't re-throw to prevent component crash
          return null;
        }
      };
    }
  };
}

/**
 * Validate and handle file operations
 */
export function handleFileError(error, filename) {
  const fileErrors = {
    'ENOENT': `File not found: ${filename}`,
    'EACCES': `Permission denied: ${filename}`,
    'EISDIR': `Expected a file but found a directory: ${filename}`,
    'ENOTDIR': `Expected a directory but found a file: ${filename}`,
    'EMFILE': 'Too many open files. Please try again later.',
    'ENOSPC': 'No space left on device.',
    'INVALID_JSON': `Invalid JSON in file: ${filename}`,
  };

  const message = fileErrors[error.code] || `File operation failed: ${filename}`;
  
  return handleError({
    ...error,
    message
  }, 'File Operation');
}

/**
 * Network error handler
 */
export function handleNetworkError(error, url) {
  const networkErrors = {
    'ECONNREFUSED': `Connection refused: ${url}`,
    'ETIMEDOUT': `Connection timed out: ${url}`,
    'ENOTFOUND': `Server not found: ${url}`,
    'ECONNRESET': `Connection reset: ${url}`,
    '401': 'Authentication required. Please log in.',
    '403': 'Access forbidden. You do not have permission.',
    '404': `Resource not found: ${url}`,
    '500': 'Internal server error. Please try again later.',
    '503': 'Service unavailable. Please try again later.',
  };

  const statusCode = error.response?.status || error.code;
  const message = networkErrors[statusCode] || `Network request failed: ${url}`;
  
  return handleError({
    ...error,
    message
  }, 'Network Request');
}