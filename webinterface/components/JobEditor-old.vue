<template>
  <div class="h-full flex flex-col" :class="theme ? theme.surface : ''">
    <!-- Header -->
    <div class="px-6 py-4 border-b flex items-center justify-between" :class="theme ? theme.border : 'border-gray-200'">
      <h2 class="text-lg font-semibold" :class="theme ? theme.text : 'text-gray-900'">Edit Job: {{ job.id }}</h2>
      <button @click="$emit('close')" class="transition-colors" :class="theme ? [theme.textMuted, 'hover:' + theme.text] : 'text-gray-400 hover:text-gray-600'">
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
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Description</label>
            <input v-model="localJob.description" type="text" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Command</label>
            <textarea v-model="localJob.command" rows="3"
                      class="w-full px-3 py-2 border rounded-lg focus:ring-2 font-mono text-sm"
                      :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'"></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Timeout (seconds)</label>
            <input v-model.number="localJob.timeout" type="number" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
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
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <button @click="removeDependency(index)" class="p-2 text-red-500 hover:text-red-700">
              <i class="fas fa-trash"></i>
            </button>
          </div>
          <button @click="addDependency" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" :class="theme ? [theme.border, theme.textMuted, 'hover:' + theme.text] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Dependency
          </button>
        </div>
      </div>
      
      <!-- Environment Variables -->
      <div class="mb-6">
        <h3 class="text-sm font-semibold uppercase tracking-wider mb-3" :class="theme ? theme.text : 'text-gray-700'">Environment Variables</h3>
        <div class="space-y-2">
          <div v-for="(value, key) in localJob.env_variables" :key="key" class="flex items-center space-x-2">
            <input v-model="envVarKeys[key]" type="text" placeholder="KEY" 
                   @blur="updateEnvVarKey(key, envVarKeys[key])"
                   class="w-1/3 px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <input v-model="localJob.env_variables[key]" type="text" placeholder="Value"
                   class="flex-1 px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <button @click="removeEnvVar(key)" class="p-2 text-red-500 hover:text-red-700">
              <i class="fas fa-trash"></i>
            </button>
          </div>
          <button @click="addEnvVar" class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" :class="theme ? [theme.border, theme.textMuted, 'hover:' + theme.text] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Environment Variable
          </button>
        </div>
      </div>
      
      <!-- Retry Configuration -->
      <div class="mb-6">
        <h3 class="text-sm font-semibold uppercase tracking-wider mb-3" :class="theme ? theme.text : 'text-gray-700'">Retry Configuration</h3>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retries</label>
            <input v-model.number="localJob.max_retries" type="number" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Delay (s)</label>
            <input v-model.number="localJob.retry_delay" type="number" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Backoff</label>
            <input v-model.number="localJob.retry_backoff" type="number" step="0.1"
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div>
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Jitter</label>
            <input v-model.number="localJob.retry_jitter" type="number" step="0.1"
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retry Time (s)</label>
            <input v-model.number="localJob.max_retry_time" type="number" 
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
          <div class="col-span-2">
            <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry on Exit Codes</label>
            <input v-model="retryExitCodes" type="text" placeholder="1,2,3"
                   class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                   :class="theme ? [theme.surface, theme.border, theme.text, 'focus:ring-' + theme.accent.replace('bg-', ''), 'focus:border-' + theme.accent.replace('bg-', '')] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
          </div>
        </div>
      </div>
      
      <!-- Checks -->
      <div class="mb-6">
        <h3 class="text-sm font-semibold uppercase tracking-wider mb-3" :class="theme ? theme.text : 'text-gray-700'">Pre/Post Checks</h3>
        <div class="mb-4">
          <h4 class="text-sm font-medium mb-2" :class="theme ? theme.textMuted : 'text-gray-600'">Pre-checks</h4>
          <button class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" :class="theme ? [theme.border, theme.textMuted, 'hover:' + theme.text] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Pre-check
          </button>
        </div>
        <div>
          <h4 class="text-sm font-medium mb-2" :class="theme ? theme.textMuted : 'text-gray-600'">Post-checks</h4>
          <button class="w-full px-3 py-2 border border-dashed rounded-lg transition-colors" :class="theme ? [theme.border, theme.textMuted, 'hover:' + theme.text] : 'border-gray-300 text-gray-500 hover:border-gray-400 hover:text-gray-600'">
            <i class="fas fa-plus mr-2"></i>Add Post-check
          </button>
        </div>
      </div>
    </div>
    
    <!-- Footer -->
    <div class="px-6 py-4 border-t flex justify-end space-x-3" :class="theme ? theme.border : 'border-gray-200'">
      <button @click="$emit('close')" 
              class="px-4 py-2 border rounded-lg transition-colors" :class="theme ? [theme.border, theme.text, theme.surfaceHover] : 'border-gray-300 text-gray-700 hover:bg-gray-50'">
        Cancel
      </button>
      <button @click="saveJob" 
              class="px-4 py-2 rounded-lg transition-colors" :class="theme ? [theme.accent, theme.accentText, theme.accentHover] : 'bg-indigo-600 text-white hover:bg-indigo-700'">
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
      localJob: JSON.parse(JSON.stringify(this.job)),
      envVarKeys: {},
      updateTimeout: null
    };
  },
  watch: {
    localJob: {
      handler(newVal) {
        // Don't emit update for every keystroke, wait for user to finish
        clearTimeout(this.updateTimeout);
        this.updateTimeout = setTimeout(() => {
          this.$emit('update', newVal);
        }, 500);
      },
      deep: true
    },
    job: {
      handler(newVal) {
        // Update local copy when prop changes (e.g., when ID is reverted)
        this.localJob = JSON.parse(JSON.stringify(newVal));
      },
      deep: true
    }
  },
  computed: {
    retryExitCodes: {
      get() {
        return (this.localJob.retry_on_exit_codes || []).join(',');
      },
      set(value) {
        this.localJob.retry_on_exit_codes = value.split(',').map(v => parseInt(v.trim())).filter(v => !isNaN(v));
      }
    }
  },
  mounted() {
    this.initEnvVarKeys();
  },
  methods: {
    initEnvVarKeys() {
      this.envVarKeys = {};
      for (const key in this.localJob.env_variables) {
        this.envVarKeys[key] = key;
      }
    },
    addDependency() {
      if (!this.localJob.dependencies) {
        this.localJob.dependencies = [];
      }
      this.localJob.dependencies.push('');
    },
    removeDependency(index) {
      this.localJob.dependencies.splice(index, 1);
    },
    addEnvVar() {
      if (!this.localJob.env_variables) {
        this.localJob.env_variables = {};
      }
      // Find a unique key
      let newKey = 'NEW_VAR';
      let counter = 1;
      while (this.localJob.env_variables.hasOwnProperty(newKey)) {
        newKey = `NEW_VAR_${counter++}`;
      }
      this.localJob.env_variables[newKey] = '';
      this.envVarKeys[newKey] = newKey;
    },
    removeEnvVar(key) {
      delete this.localJob.env_variables[key];
      delete this.envVarKeys[key];
    },
    updateEnvVarKey(oldKey, newKey) {
      if (oldKey === newKey || !newKey) return;
      
      if (this.localJob.env_variables.hasOwnProperty(newKey)) {
        alert(`Environment variable "${newKey}" already exists`);
        this.envVarKeys[oldKey] = oldKey;
        return;
      }
      
      const value = this.localJob.env_variables[oldKey];
      delete this.localJob.env_variables[oldKey];
      delete this.envVarKeys[oldKey];
      
      this.localJob.env_variables[newKey] = value;
      this.envVarKeys[newKey] = newKey;
    },
    saveJob() {
      this.$emit('update', this.localJob);
      this.$emit('close');
    }
  }
};
</script>