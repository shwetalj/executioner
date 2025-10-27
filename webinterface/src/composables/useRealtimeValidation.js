/**
 * Composable for real-time configuration validation
 * Provides live feedback as users modify configuration
 */

import { ref, computed, watch, reactive } from 'vue';
import { 
  validateJobConfig,
  validateJobId,
  validateCommand,
  validateTimeout,
  validateEnvVariables,
  validateEmailConfig
} from '../utils/validation.js';
import { useDebouncedEvent } from './useEventListener.js';

/**
 * Real-time validation for job configuration
 */
export function useRealtimeJobValidation(job) {
  const errors = reactive({});
  const warnings = reactive({});
  const validationState = ref('idle'); // 'idle', 'validating', 'valid', 'invalid'
  const lastValidation = ref(null);

  // Track field-level validation states
  const fieldStates = reactive({});

  /**
   * Validate a specific field
   */
  const validateField = (fieldName, value, immediate = false) => {
    // Mark field as validating
    fieldStates[fieldName] = 'validating';

    const performValidation = () => {
      let result = { valid: true };
      
      switch (fieldName) {
        case 'id':
          result = validateJobId(value);
          break;
        case 'command':
          result = validateCommand(value);
          break;
        case 'timeout':
          result = validateTimeout(value);
          break;
        case 'env_variables':
          result = validateEnvVariables(value);
          break;
        default:
          // For nested fields or unknown fields
          result = { valid: true };
      }

      // Update errors and warnings
      if (!result.valid) {
        errors[fieldName] = result.error;
        delete warnings[fieldName];
        fieldStates[fieldName] = 'invalid';
      } else {
        delete errors[fieldName];
        if (result.warnings?.length > 0) {
          warnings[fieldName] = result.warnings[0];
          fieldStates[fieldName] = 'warning';
        } else {
          delete warnings[fieldName];
          fieldStates[fieldName] = 'valid';
        }
      }

      updateOverallState();
    };

    if (immediate) {
      performValidation();
    } else {
      // Debounce validation for better UX
      setTimeout(performValidation, 300);
    }
  };

  /**
   * Validate entire configuration
   */
  const validateAll = () => {
    validationState.value = 'validating';
    
    const result = validateJobConfig(job.value || job);
    
    // Clear existing errors and warnings
    Object.keys(errors).forEach(key => delete errors[key]);
    Object.keys(warnings).forEach(key => delete warnings[key]);
    
    // Add new errors
    if (!result.valid) {
      result.errors.forEach((error, index) => {
        errors[`error_${index}`] = error;
      });
    }
    
    // Add new warnings
    if (result.warnings?.length > 0) {
      result.warnings.forEach((warning, index) => {
        warnings[`warning_${index}`] = warning;
      });
    }
    
    // Update state
    validationState.value = result.valid ? 'valid' : 'invalid';
    lastValidation.value = new Date();
    
    return result;
  };

  /**
   * Update overall validation state
   */
  const updateOverallState = () => {
    if (Object.keys(errors).length > 0) {
      validationState.value = 'invalid';
    } else if (Object.keys(warnings).length > 0) {
      validationState.value = 'warning';
    } else {
      validationState.value = 'valid';
    }
  };

  /**
   * Get validation status for a field
   */
  const getFieldStatus = (fieldName) => {
    return fieldStates[fieldName] || 'idle';
  };

  /**
   * Get field validation classes
   */
  const getFieldClasses = (fieldName, baseClasses = '') => {
    const status = getFieldStatus(fieldName);
    const statusClasses = {
      idle: '',
      validating: 'border-blue-300 animate-pulse',
      valid: 'border-green-300 focus:ring-green-500',
      invalid: 'border-red-300 focus:ring-red-500',
      warning: 'border-yellow-300 focus:ring-yellow-500'
    };
    
    return `${baseClasses} ${statusClasses[status] || ''}`.trim();
  };

  /**
   * Check if configuration is valid
   */
  const isValid = computed(() => {
    return Object.keys(errors).length === 0 && validationState.value !== 'invalid';
  });

  /**
   * Check if there are warnings
   */
  const hasWarnings = computed(() => {
    return Object.keys(warnings).length > 0;
  });

  /**
   * Get validation summary
   */
  const validationSummary = computed(() => {
    const errorCount = Object.keys(errors).length;
    const warningCount = Object.keys(warnings).length;
    
    if (errorCount === 0 && warningCount === 0) {
      return { type: 'success', message: 'Configuration is valid' };
    } else if (errorCount > 0) {
      return { 
        type: 'error', 
        message: `${errorCount} error${errorCount > 1 ? 's' : ''} found`,
        details: Object.values(errors)
      };
    } else {
      return { 
        type: 'warning', 
        message: `${warningCount} warning${warningCount > 1 ? 's' : ''}`,
        details: Object.values(warnings)
      };
    }
  });

  /**
   * Clear validation state
   */
  const clearValidation = () => {
    Object.keys(errors).forEach(key => delete errors[key]);
    Object.keys(warnings).forEach(key => delete warnings[key]);
    Object.keys(fieldStates).forEach(key => delete fieldStates[key]);
    validationState.value = 'idle';
  };

  return {
    errors,
    warnings,
    validationState,
    fieldStates,
    lastValidation,
    isValid,
    hasWarnings,
    validationSummary,
    validateField,
    validateAll,
    getFieldStatus,
    getFieldClasses,
    clearValidation
  };
}

/**
 * Real-time validation for application configuration
 */
export function useRealtimeAppValidation(config) {
  const errors = reactive({});
  const warnings = reactive({});
  const validationState = ref('idle');

  /**
   * Validate email configuration
   */
  const validateEmailSettings = () => {
    if (!config.value) return;
    
    const emailConfig = {
      email_address: config.value.email_address,
      smtp_server: config.value.smtp_server,
      smtp_port: config.value.smtp_port
    };
    
    const result = validateEmailConfig(emailConfig);
    
    if (!result.valid) {
      errors.email = result.errors[0];
    } else {
      delete errors.email;
    }
  };

  /**
   * Validate parallel execution settings
   */
  const validateParallelSettings = () => {
    if (!config.value) return;
    
    if (config.value.parallel && config.value.max_workers) {
      const workers = Number(config.value.max_workers);
      if (isNaN(workers) || workers < 1 || workers > 100) {
        errors.max_workers = 'Max workers must be between 1 and 100';
      } else {
        delete errors.max_workers;
      }
    }
  };

  /**
   * Validate environment variables
   */
  const validateEnvSettings = () => {
    if (!config.value?.env_variables) return;
    
    const result = validateEnvVariables(config.value.env_variables);
    
    if (!result.valid) {
      errors.env_variables = result.errors[0];
    } else {
      delete errors.env_variables;
      if (result.warnings?.length > 0) {
        warnings.env_variables = result.warnings[0];
      }
    }
  };

  /**
   * Validate all application settings
   */
  const validateAll = () => {
    validationState.value = 'validating';
    
    // Clear existing errors
    Object.keys(errors).forEach(key => delete errors[key]);
    Object.keys(warnings).forEach(key => delete warnings[key]);
    
    // Run all validations
    validateEmailSettings();
    validateParallelSettings();
    validateEnvSettings();
    
    // Update state
    validationState.value = Object.keys(errors).length === 0 ? 'valid' : 'invalid';
    
    return {
      valid: Object.keys(errors).length === 0,
      errors: Object.values(errors),
      warnings: Object.values(warnings)
    };
  };

  // Watch for changes and validate
  if (config.value) {
    watch(config, () => {
      validateAll();
    }, { deep: true });
  }

  const isValid = computed(() => Object.keys(errors).length === 0);

  return {
    errors,
    warnings,
    validationState,
    isValid,
    validateAll,
    validateEmailSettings,
    validateParallelSettings,
    validateEnvSettings
  };
}

/**
 * Circular dependency detection
 */
export function useCircularDependencyDetection(jobs) {
  const circularDependencies = ref([]);
  
  /**
   * Check for circular dependencies using DFS
   */
  const detectCircularDependencies = () => {
    const visited = new Set();
    const recursionStack = new Set();
    const circular = [];
    
    const hasCycle = (jobId, path = []) => {
      if (recursionStack.has(jobId)) {
        // Found a cycle
        const cycleStart = path.indexOf(jobId);
        const cycle = path.slice(cycleStart).concat(jobId);
        circular.push(cycle);
        return true;
      }
      
      if (visited.has(jobId)) {
        return false;
      }
      
      visited.add(jobId);
      recursionStack.add(jobId);
      
      const job = jobs.value.find(j => j.id === jobId);
      if (job?.dependencies) {
        for (const dep of job.dependencies) {
          if (hasCycle(dep, [...path, jobId])) {
            return true;
          }
        }
      }
      
      recursionStack.delete(jobId);
      return false;
    };
    
    // Check all jobs
    for (const job of jobs.value) {
      if (!visited.has(job.id)) {
        hasCycle(job.id);
      }
    }
    
    circularDependencies.value = circular;
    return circular.length === 0;
  };
  
  /**
   * Check if adding a dependency would create a cycle
   */
  const wouldCreateCycle = (fromJobId, toJobId) => {
    // Check if there's already a path from toJobId to fromJobId
    const visited = new Set();
    const queue = [toJobId];
    
    while (queue.length > 0) {
      const current = queue.shift();
      
      if (current === fromJobId) {
        return true; // Would create a cycle
      }
      
      if (!visited.has(current)) {
        visited.add(current);
        const job = jobs.value.find(j => j.id === current);
        if (job?.dependencies) {
          queue.push(...job.dependencies);
        }
      }
    }
    
    return false;
  };
  
  // Auto-detect when jobs change
  if (jobs.value) {
    watch(jobs, detectCircularDependencies, { deep: true, immediate: true });
  }
  
  return {
    circularDependencies,
    detectCircularDependencies,
    wouldCreateCycle,
    hasCircularDependencies: computed(() => circularDependencies.value.length > 0)
  };
}

/**
 * Duplicate job ID detection
 */
export function useDuplicateIdDetection(jobs) {
  const duplicateIds = ref([]);
  
  const detectDuplicates = () => {
    const idCounts = {};
    const duplicates = [];
    
    for (const job of jobs.value) {
      if (job.id) {
        idCounts[job.id] = (idCounts[job.id] || 0) + 1;
      }
    }
    
    for (const [id, count] of Object.entries(idCounts)) {
      if (count > 1) {
        duplicates.push({ id, count });
      }
    }
    
    duplicateIds.value = duplicates;
    return duplicates.length === 0;
  };
  
  // Auto-detect when jobs change
  if (jobs.value) {
    watch(jobs, detectDuplicates, { deep: true, immediate: true });
  }
  
  return {
    duplicateIds,
    detectDuplicates,
    hasDuplicates: computed(() => duplicateIds.value.length > 0),
    isDuplicate: (jobId) => duplicateIds.value.some(d => d.id === jobId)
  };
}