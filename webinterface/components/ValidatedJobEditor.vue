<template>
  <div class="h-full flex flex-col" :class="theme ? theme.surface : 'bg-white'">
    <div class="px-6 py-4 border-b flex items-center justify-between" :class="theme ? theme.border : 'border-gray-200'">
      <h3 class="text-lg font-semibold" :class="theme ? theme.text : 'text-gray-900'">Edit Job: {{ localJob.id || 'New Job' }}</h3>
      <button @click="$emit('cancel')" class="transition-colors" :class="theme ? [theme.textMuted, 'hover:' + theme.text] : 'text-gray-400 hover:text-gray-600'" aria-label="Close job editor">
        <i class="fas fa-times text-xl"></i>
      </button>
    </div>
    <div class="flex-1 overflow-y-auto p-6">
    
    <!-- Job ID -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">
        Job ID <span class="text-red-500">*</span>
      </label>
      <input
        v-model="localJob.id"
        @blur="validateField('id')"
        type="text"
        class="w-full px-3 py-2 border rounded-lg focus:ring-2"
        :class="getFieldClass('id')"
        placeholder="e.g., download_data"
      />
      <p v-if="errors.id" class="mt-1 text-sm text-red-600">{{ errors.id }}</p>
    </div>

    <!-- Description -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">Description</label>
      <input
        v-model="localJob.description"
        type="text"
        class="w-full px-3 py-2 border rounded-lg focus:ring-2 border-gray-300 focus:ring-indigo-500"
        placeholder="Brief description of the job"
      />
    </div>

    <!-- Command -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">
        Command <span class="text-red-500">*</span>
      </label>
      <div class="relative">
        <textarea
          v-model="localJob.command"
          @blur="validateField('command')"
          rows="3"
          class="w-full px-3 py-2 border rounded-lg focus:ring-2 font-mono text-sm"
          :class="getFieldClass('command')"
          placeholder="e.g., python script.py"
        ></textarea>
        <div v-if="warnings.command" class="absolute top-2 right-2">
          <svg class="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
        </div>
      </div>
      <p v-if="errors.command" class="mt-1 text-sm text-red-600">{{ errors.command }}</p>
      <p v-if="warnings.command" class="mt-1 text-sm text-yellow-600">{{ warnings.command }}</p>
    </div>

    <!-- Dependencies -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">Dependencies</label>
      <div class="space-y-2">
        <div v-for="(dep, index) in localJob.dependencies" :key="index" class="flex items-center space-x-2">
          <input
            v-model="localJob.dependencies[index]"
            @blur="validateField('dependencies')"
            type="text"
            class="flex-1 px-3 py-2 border rounded-lg focus:ring-2"
            :class="getFieldClass(`dependencies.${index}`)"
            placeholder="Job ID"
          />
          <button
            @click="removeDependency(index)"
            class="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
        <button
          @click="addDependency"
          class="w-full py-2 px-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-indigo-500 transition-colors"
        >
          + Add Dependency
        </button>
      </div>
      <p v-if="errors.dependencies" class="mt-1 text-sm text-red-600">{{ errors.dependencies }}</p>
    </div>

    <!-- Timeout -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">Timeout (seconds)</label>
      <input
        v-model.number="localJob.timeout"
        @blur="validateField('timeout')"
        type="number"
        min="0"
        max="86400"
        class="w-full px-3 py-2 border rounded-lg focus:ring-2"
        :class="getFieldClass('timeout')"
        placeholder="300"
      />
      <p v-if="errors.timeout" class="mt-1 text-sm text-red-600">{{ errors.timeout }}</p>
    </div>

    <!-- Retry Configuration -->
    <div class="mb-4">
      <h4 class="text-sm font-medium mb-2">Retry Configuration</h4>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs text-gray-600 mb-1">Max Retries</label>
          <input
            v-model.number="localJob.max_retries"
            @blur="validateField('max_retries')"
            type="number"
            min="0"
            max="10"
            class="w-full px-3 py-2 border rounded-lg focus:ring-2 text-sm"
            :class="getFieldClass('max_retries')"
          />
        </div>
        <div>
          <label class="block text-xs text-gray-600 mb-1">Retry Delay (s)</label>
          <input
            v-model.number="localJob.retry_delay"
            @blur="validateField('retry_delay')"
            type="number"
            min="0"
            max="3600"
            class="w-full px-3 py-2 border rounded-lg focus:ring-2 text-sm"
            :class="getFieldClass('retry_delay')"
          />
        </div>
      </div>
      <p v-if="errors.retry" class="mt-1 text-sm text-red-600">{{ errors.retry }}</p>
    </div>

    <!-- Environment Variables -->
    <div class="mb-4">
      <label class="block text-sm font-medium mb-1">Environment Variables</label>
      <div class="space-y-2">
        <div v-for="(value, key) in localJob.env_variables" :key="key" class="flex items-center space-x-2">
          <input
            :value="key"
            @input="updateEnvKey(key, $event.target.value)"
            type="text"
            class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
            :class="getFieldClass(`env.${key}`)"
            placeholder="KEY"
          />
          <input
            v-model="localJob.env_variables[key]"
            :type="isSensitiveField(key) ? 'password' : 'text'"
            class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
            placeholder="value"
          />
          <button
            @click="removeEnvVariable(key)"
            class="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <button
          @click="addEnvVariable"
          class="w-full py-2 px-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-indigo-500 transition-colors"
        >
          + Add Environment Variable
        </button>
      </div>
      <p v-if="errors.env_variables" class="mt-1 text-sm text-red-600">{{ errors.env_variables }}</p>
      <p v-if="warnings.env_variables" class="mt-1 text-sm text-yellow-600">{{ warnings.env_variables }}</p>
    </div>

    <!-- Validation Summary -->
    <div v-if="showValidationSummary" class="mb-4 p-4 rounded-lg"
         :class="isValid ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'">
      <div class="flex items-center">
        <svg v-if="isValid" class="w-5 h-5 text-green-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
        </svg>
        <svg v-else class="w-5 h-5 text-red-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <span :class="isValid ? 'text-green-800' : 'text-red-800'">
          {{ isValid ? 'Configuration is valid' : 'Please fix the errors before saving' }}
        </span>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="flex justify-end space-x-3">
      <button
        @click="$emit('cancel')"
        class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        Cancel
      </button>
      <button
        @click="validateAndSave"
        :disabled="!isValid && showValidationSummary"
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Save Job
      </button>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { 
  validateJobId, 
  validateCommand, 
  validateTimeout, 
  validateRetryConfig,
  validateEnvVariables,
  validateJobConfig 
} from '../src/utils/validation.js';
import { isSensitiveField } from '../src/utils/security.js';
import { showNotification } from '../src/utils/errorHandler.js';

const props = defineProps({
  job: {
    type: Object,
    default: () => ({
      id: '',
      description: '',
      command: '',
      dependencies: [],
      timeout: 300,
      max_retries: 2,
      retry_delay: 30,
      env_variables: {}
    })
  },
  theme: {
    type: Object,
    default: null
  }
});

const emit = defineEmits(['save', 'cancel']);

const localJob = ref(JSON.parse(JSON.stringify(props.job)));
const errors = ref({});
const warnings = ref({});
const showValidationSummary = ref(false);

const isValid = computed(() => {
  return Object.keys(errors.value).length === 0 && 
         localJob.value.id && 
         localJob.value.command;
});

const getFieldClass = (field) => {
  if (errors.value[field]) {
    return 'border-red-300 focus:ring-red-500 focus:border-red-500';
  }
  if (warnings.value[field]) {
    return 'border-yellow-300 focus:ring-yellow-500 focus:border-yellow-500';
  }
  return 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500';
};

const validateField = (field) => {
  // Clear previous errors for this field
  delete errors.value[field];
  delete warnings.value[field];

  switch(field) {
    case 'id':
      const idResult = validateJobId(localJob.value.id);
      if (!idResult.valid) {
        errors.value.id = idResult.error;
      }
      break;
      
    case 'command':
      const cmdResult = validateCommand(localJob.value.command);
      if (!cmdResult.valid) {
        errors.value.command = cmdResult.error;
      } else if (cmdResult.warnings?.length > 0) {
        warnings.value.command = cmdResult.warnings[0];
      }
      break;
      
    case 'timeout':
      if (localJob.value.timeout !== undefined) {
        const timeoutResult = validateTimeout(localJob.value.timeout);
        if (!timeoutResult.valid) {
          errors.value.timeout = timeoutResult.error;
        }
      }
      break;
      
    case 'dependencies':
      if (localJob.value.dependencies?.length > 0) {
        for (const dep of localJob.value.dependencies) {
          const depResult = validateJobId(dep);
          if (!depResult.valid) {
            errors.value.dependencies = `Invalid dependency: ${dep}`;
            break;
          }
        }
      }
      break;
      
    case 'max_retries':
    case 'retry_delay':
      const retryResult = validateRetryConfig(localJob.value);
      if (!retryResult.valid) {
        errors.value.retry = retryResult.errors[0];
      }
      break;
      
    case 'env_variables':
      const envResult = validateEnvVariables(localJob.value.env_variables);
      if (!envResult.valid) {
        errors.value.env_variables = envResult.errors[0];
      } else if (envResult.warnings?.length > 0) {
        warnings.value.env_variables = envResult.warnings[0];
      }
      break;
  }
};

const validateAll = () => {
  const result = validateJobConfig(localJob.value);
  
  errors.value = {};
  warnings.value = {};
  
  if (!result.valid) {
    result.errors.forEach((error, index) => {
      errors.value[`error_${index}`] = error;
    });
  }
  
  if (result.warnings?.length > 0) {
    result.warnings.forEach((warning, index) => {
      warnings.value[`warning_${index}`] = warning;
    });
  }
  
  showValidationSummary.value = true;
  
  return result.valid;
};

const validateAndSave = () => {
  if (validateAll()) {
    emit('save', localJob.value);
    showNotification('Job configuration saved successfully', 'success');
  } else {
    showNotification('Please fix validation errors before saving', 'error');
  }
};

const addDependency = () => {
  if (!localJob.value.dependencies) {
    localJob.value.dependencies = [];
  }
  localJob.value.dependencies.push('');
};

const removeDependency = (index) => {
  localJob.value.dependencies.splice(index, 1);
  validateField('dependencies');
};

const addEnvVariable = () => {
  if (!localJob.value.env_variables) {
    localJob.value.env_variables = {};
  }
  const newKey = `NEW_VAR_${Object.keys(localJob.value.env_variables).length + 1}`;
  localJob.value.env_variables[newKey] = '';
};

const removeEnvVariable = (key) => {
  delete localJob.value.env_variables[key];
  validateField('env_variables');
};

const updateEnvKey = (oldKey, newKey) => {
  if (oldKey !== newKey && newKey) {
    const value = localJob.value.env_variables[oldKey];
    delete localJob.value.env_variables[oldKey];
    localJob.value.env_variables[newKey] = value;
    validateField('env_variables');
  }
};

// Watch for changes to reset validation summary
watch(localJob, () => {
  showValidationSummary.value = false;
}, { deep: true });

// Watch for prop changes to update localJob when a different job is selected
watch(() => props.job, (newJob) => {
  // Update localJob with the new job data
  localJob.value = JSON.parse(JSON.stringify(newJob));
  // Reset validation state
  errors.value = {};
  warnings.value = {};
  showValidationSummary.value = false;
}, { deep: true });
</script>