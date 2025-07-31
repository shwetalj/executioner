<template>
  <div class="h-full flex flex-col" :class="theme ? theme.surface : ''">
    <!-- Header -->
    <div class="px-6 py-4 border-b flex items-center justify-between" :class="theme ? theme.border : 'border-gray-200'">
      <h2 class="text-lg font-semibold" :class="theme ? theme.text : 'text-gray-900'">Edit Job: {{ job.id }}</h2>
      <button @click="$emit('close')" class="transition-colors" :class="theme ? [theme.textMuted, 'hover:text-gray-600'] : 'text-gray-400 hover:text-gray-600'">
        <i class="fas fa-times"></i>
      </button>
    </div>
    
    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-6">
      <!-- Basic Information -->
      <div class="mb-6">
        <h3 class="text-sm font-semibold uppercase tracking-wider mb-3" :class="theme ? theme.text : 'text-gray-700'">Basic Information</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Job ID</label>
            <input v-model="localJob.id" type="text" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Description</label>
            <input v-model="localJob.description" type="text" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Command</label>
            <textarea v-model="localJob.command" rows="3"
                      class="w-full px-3 py-2 border rounded-lg focus:ring-2 font-mono text-sm"
                      :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'"></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Timeout (seconds)</label>
            <input v-model.number="localJob.timeout" type="number" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
        </div>
      </div>
      
      <!-- Dependencies -->
      <div class="mb-6">
        <h3 class="text-sm font-semibold uppercase tracking-wider mb-3" :class="theme ? theme.text : 'text-gray-700'">Dependencies</h3>
        <div class="space-y-2">
          <div v-for="(dep, index) in localJob.dependencies" :key="index" class="flex items-center space-x-2">
            <input v-model="localJob.dependencies[index]" type="text" placeholder="Job ID"
                   class="flex-1 px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <button @click="removeDependency(index)" class="p-2 text-red-500 hover:text-red-700">
              <i class="fas fa-trash"></i>
            </button>
          </div>
          <button @click="addDependency" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" 
                  :class="theme ? [theme.border, theme.textMuted, theme.surfaceHover] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Dependency
          </button>
        </div>
      </div>

      <!-- Environment Variables -->
      <div class="mb-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold uppercase tracking-wider" :class="theme ? theme.text : 'text-gray-700'">Environment Variables</h3>
          <button @click="showEnvVars = !showEnvVars" class="text-sm" :class="theme ? theme.textMuted : 'text-gray-500'">
            <i :class="showEnvVars ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
          </button>
        </div>
        <div v-if="showEnvVars" class="space-y-2">
          <div v-for="(value, key) in localJob.env_variables" :key="key" class="flex items-center space-x-2">
            <input v-model="envVarKeys[key]" @blur="updateEnvVarKey(key, envVarKeys[key])" type="text" placeholder="Key"
                   class="w-1/3 px-3 py-2 border rounded-lg focus:ring-2 font-mono text-sm"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <input v-model="localJob.env_variables[key]" type="text" placeholder="Value"
                   class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 font-mono text-sm"
                   :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <button @click="removeEnvVar(key)" class="p-2 text-red-500 hover:text-red-700">
              <i class="fas fa-trash"></i>
            </button>
          </div>
          <button @click="addEnvVar" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" 
                  :class="theme ? [theme.border, theme.textMuted, theme.surfaceHover] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Environment Variable
          </button>
        </div>
      </div>

      <!-- Pre-checks -->
      <div class="mb-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold uppercase tracking-wider" :class="theme ? theme.text : 'text-gray-700'">Pre-execution Checks</h3>
          <button @click="showPreChecks = !showPreChecks" class="text-sm" :class="theme ? theme.textMuted : 'text-gray-500'">
            <i :class="showPreChecks ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
          </button>
        </div>
        <div v-if="showPreChecks" class="space-y-2">
          <div v-for="(check, index) in localJob.pre_checks" :key="index" class="border rounded-lg p-3" :class="theme ? theme.border : 'border-gray-200'">
            <div class="flex items-start justify-between">
              <div class="flex-1 space-y-2">
                <input v-model="check.name" type="text" placeholder="Check name (e.g., check_file_exists)"
                       class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                       :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                <div v-for="(value, key) in check.params" :key="key" class="flex items-center space-x-2">
                  <input v-model="checkParamKeys[`pre_${index}_${key}`]" @blur="updateCheckParamKey(check, key, checkParamKeys[`pre_${index}_${key}`])" type="text" placeholder="Param key"
                         class="w-1/3 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
                         :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                  <input v-model="check.params[key]" type="text" placeholder="Param value"
                         class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
                         :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                  <button @click="removeCheckParam(check, key)" class="p-1 text-red-500 hover:text-red-700">
                    <i class="fas fa-times"></i>
                  </button>
                </div>
                <button @click="addCheckParam(check)" class="text-sm px-2 py-1 rounded" :class="theme ? [theme.textMuted, theme.surfaceHover] : 'text-gray-500 hover:bg-gray-100'">
                  <i class="fas fa-plus mr-1"></i>Add Parameter
                </button>
              </div>
              <button @click="removePreCheck(index)" class="ml-2 p-2 text-red-500 hover:text-red-700">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <button @click="addPreCheck" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" 
                  :class="theme ? [theme.border, theme.textMuted, theme.surfaceHover] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Pre-check
          </button>
        </div>
      </div>

      <!-- Post-checks -->
      <div class="mb-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold uppercase tracking-wider" :class="theme ? theme.text : 'text-gray-700'">Post-execution Checks</h3>
          <button @click="showPostChecks = !showPostChecks" class="text-sm" :class="theme ? theme.textMuted : 'text-gray-500'">
            <i :class="showPostChecks ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
          </button>
        </div>
        <div v-if="showPostChecks" class="space-y-2">
          <div v-for="(check, index) in localJob.post_checks" :key="index" class="border rounded-lg p-3" :class="theme ? theme.border : 'border-gray-200'">
            <div class="flex items-start justify-between">
              <div class="flex-1 space-y-2">
                <input v-model="check.name" type="text" placeholder="Check name (e.g., check_no_ora_errors)"
                       class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                       :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                <div v-for="(value, key) in check.params" :key="key" class="flex items-center space-x-2">
                  <input v-model="checkParamKeys[`post_${index}_${key}`]" @blur="updateCheckParamKey(check, key, checkParamKeys[`post_${index}_${key}`])" type="text" placeholder="Param key"
                         class="w-1/3 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
                         :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                  <input v-model="check.params[key]" type="text" placeholder="Param value"
                         class="flex-1 px-3 py-2 border rounded-lg focus:ring-2 text-sm"
                         :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                  <button @click="removeCheckParam(check, key)" class="p-1 text-red-500 hover:text-red-700">
                    <i class="fas fa-times"></i>
                  </button>
                </div>
                <button @click="addCheckParam(check)" class="text-sm px-2 py-1 rounded" :class="theme ? [theme.textMuted, theme.surfaceHover] : 'text-gray-500 hover:bg-gray-100'">
                  <i class="fas fa-plus mr-1"></i>Add Parameter
                </button>
              </div>
              <button @click="removePostCheck(index)" class="ml-2 p-2 text-red-500 hover:text-red-700">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <button @click="addPostCheck" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" 
                  :class="theme ? [theme.border, theme.textMuted, theme.surfaceHover] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Post-check
          </button>
        </div>
      </div>

      <!-- Retry Configuration -->
      <div class="mb-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold uppercase tracking-wider" :class="theme ? theme.text : 'text-gray-700'">Retry Configuration</h3>
          <button @click="showRetryConfig = !showRetryConfig" class="text-sm" :class="theme ? theme.textMuted : 'text-gray-500'">
            <i :class="showRetryConfig ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
          </button>
        </div>
        <div v-if="showRetryConfig" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retries</label>
              <input v-model.number="localJob.max_retries" type="number" min="0"
                     class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                     :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            </div>
            <div>
              <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Delay (seconds)</label>
              <input v-model.number="localJob.retry_delay" type="number" min="0"
                     class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                     :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            </div>
            <div>
              <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Backoff</label>
              <input v-model.number="localJob.retry_backoff" type="number" min="1" step="0.1"
                     class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                     :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            </div>
            <div>
              <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Jitter</label>
              <input v-model.number="localJob.retry_jitter" type="number" min="0" max="1" step="0.1"
                     class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                     :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            </div>
            <div>
              <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retry Time (seconds)</label>
              <input v-model.number="localJob.max_retry_time" type="number" min="0"
                     class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                     :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            </div>
          </div>
          
          <!-- Retry on Status -->
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry on Status</label>
            <div class="flex flex-wrap gap-2">
              <label v-for="status in ['ERROR', 'FAILED', 'TIMEOUT']" :key="status" class="flex items-center">
                <input type="checkbox" :value="status" v-model="localJob.retry_on_status"
                       class="mr-2 rounded" :class="theme ? theme.accent : 'text-indigo-600'">
                <span class="text-sm" :class="theme ? theme.text : 'text-gray-700'">{{ status }}</span>
              </label>
            </div>
          </div>
          
          <!-- Retry on Exit Codes -->
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry on Exit Codes</label>
            <div class="space-y-2">
              <div v-for="(code, index) in localJob.retry_on_exit_codes" :key="index" class="flex items-center space-x-2">
                <input v-model.number="localJob.retry_on_exit_codes[index]" type="number" placeholder="Exit code"
                       class="flex-1 px-3 py-2 border rounded-lg focus:ring-2"
                       :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
                <button @click="removeExitCode(index)" class="p-2 text-red-500 hover:text-red-700">
                  <i class="fas fa-trash"></i>
                </button>
              </div>
              <button @click="addExitCode" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" 
                      :class="theme ? [theme.border, theme.textMuted, theme.surfaceHover] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
                <i class="fas fa-plus mr-2"></i>Add Exit Code
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Footer -->
    <div class="px-6 py-4 border-t flex justify-end space-x-3" :class="theme ? theme.border : 'border-gray-200'">
      <button @click="$emit('close')" 
              class="px-4 py-2 border rounded-lg transition-colors" 
              :class="theme ? [theme.surface, theme.border, theme.text, theme.surfaceHover] : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'">
        Cancel
      </button>
      <button @click="saveJob" 
              class="px-4 py-2 rounded-lg transition-colors" 
              :class="theme ? [theme.accent, theme.accentText, theme.accentHover] : 'bg-indigo-600 text-white hover:bg-indigo-700'">
        Save Changes
      </button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'JobEditor',
  props: {
    job: {
      type: Object,
      required: true
    },
    theme: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      localJob: this.initializeJob(),
      envVarKeys: {},
      checkParamKeys: {},
      updateTimeout: null,
      showEnvVars: true,
      showPreChecks: false,
      showPostChecks: false,
      showRetryConfig: false
    };
  },
  watch: {
    localJob: {
      handler(newVal) {
        clearTimeout(this.updateTimeout);
        this.updateTimeout = setTimeout(() => {
          this.$emit('update', newVal);
        }, 500);
      },
      deep: true
    },
    job: {
      handler(newVal) {
        this.localJob = this.initializeJob(newVal);
        this.initializeKeys();
      },
      deep: true
    }
  },
  mounted() {
    this.initializeKeys();
  },
  methods: {
    initializeJob(job = this.job) {
      const defaultJob = {
        id: '',
        description: '',
        command: '',
        timeout: null,
        dependencies: [],
        env_variables: {},
        pre_checks: [],
        post_checks: [],
        max_retries: null,
        retry_delay: null,
        retry_backoff: null,
        retry_jitter: null,
        max_retry_time: null,
        retry_on_status: [],
        retry_on_exit_codes: []
      };
      return { ...defaultJob, ...JSON.parse(JSON.stringify(job)) };
    },
    initializeKeys() {
      // Initialize env var keys
      if (this.localJob.env_variables) {
        Object.keys(this.localJob.env_variables).forEach(key => {
          this.envVarKeys[key] = key;
        });
      }
      
      // Initialize check param keys
      ['pre_checks', 'post_checks'].forEach(checkType => {
        if (this.localJob[checkType]) {
          this.localJob[checkType].forEach((check, index) => {
            if (check.params) {
              Object.keys(check.params).forEach(key => {
                this.checkParamKeys[`${checkType.replace('_checks', '')}_${index}_${key}`] = key;
              });
            }
          });
        }
      });
    },
    // Dependencies
    addDependency() {
      if (!this.localJob.dependencies) {
        this.localJob.dependencies = [];
      }
      this.localJob.dependencies.push('');
    },
    removeDependency(index) {
      this.localJob.dependencies.splice(index, 1);
    },
    // Environment Variables
    addEnvVar() {
      if (!this.localJob.env_variables) {
        this.localJob.env_variables = {};
      }
      const newKey = `NEW_VAR_${Object.keys(this.localJob.env_variables).length + 1}`;
      this.$set(this.localJob.env_variables, newKey, '');
      this.$set(this.envVarKeys, newKey, newKey);
    },
    removeEnvVar(key) {
      this.$delete(this.localJob.env_variables, key);
      this.$delete(this.envVarKeys, key);
    },
    updateEnvVarKey(oldKey, newKey) {
      if (oldKey !== newKey && newKey) {
        const value = this.localJob.env_variables[oldKey];
        this.$delete(this.localJob.env_variables, oldKey);
        this.$set(this.localJob.env_variables, newKey, value);
        this.$delete(this.envVarKeys, oldKey);
        this.$set(this.envVarKeys, newKey, newKey);
      }
    },
    // Pre-checks
    addPreCheck() {
      if (!this.localJob.pre_checks) {
        this.localJob.pre_checks = [];
      }
      this.localJob.pre_checks.push({ name: '', params: {} });
    },
    removePreCheck(index) {
      this.localJob.pre_checks.splice(index, 1);
    },
    // Post-checks
    addPostCheck() {
      if (!this.localJob.post_checks) {
        this.localJob.post_checks = [];
      }
      this.localJob.post_checks.push({ name: '', params: {} });
    },
    removePostCheck(index) {
      this.localJob.post_checks.splice(index, 1);
    },
    // Check parameters
    addCheckParam(check) {
      if (!check.params) {
        this.$set(check, 'params', {});
      }
      const newKey = `param${Object.keys(check.params).length + 1}`;
      this.$set(check.params, newKey, '');
    },
    removeCheckParam(check, key) {
      this.$delete(check.params, key);
    },
    updateCheckParamKey(check, oldKey, newKey) {
      if (oldKey !== newKey && newKey) {
        const value = check.params[oldKey];
        this.$delete(check.params, oldKey);
        this.$set(check.params, newKey, value);
      }
    },
    // Exit codes
    addExitCode() {
      if (!this.localJob.retry_on_exit_codes) {
        this.localJob.retry_on_exit_codes = [];
      }
      this.localJob.retry_on_exit_codes.push(1);
    },
    removeExitCode(index) {
      this.localJob.retry_on_exit_codes.splice(index, 1);
    },
    saveJob() {
      this.$emit('update', this.localJob);
      this.$emit('close');
    }
  }
};
</script>

<style scoped>
/* Webkit browsers (Chrome, Safari, Edge) */
.overflow-y-auto::-webkit-scrollbar {
  width: 16px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 10px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* Firefox */
.overflow-y-auto {
  scrollbar-width: thick;
  scrollbar-color: #888 #f1f1f1;
}
</style>