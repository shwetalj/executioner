<template>
  <div class="p-6 max-w-4xl mx-auto">
    <h2 class="text-2xl font-bold mb-6" :class="theme ? theme.text : 'text-gray-900'">Application Configuration</h2>
    
    <!-- Basic Configuration -->
    <div class="rounded-lg shadow-sm border p-6 mb-6" :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
      <h3 class="text-lg font-semibold mb-4" :class="theme ? theme.text : 'text-gray-900'">Basic Configuration</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Application Name</label>
          <input v-model="localConfig.application_name" type="text" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Log Directory</label>
          <input v-model="localConfig.log_dir" type="text" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
      </div>
    </div>

    <!-- Execution Settings -->
    <div class="rounded-lg shadow-sm border p-6 mb-6" :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
      <h3 class="text-lg font-semibold mb-4" :class="theme ? theme.text : 'text-gray-900'">Execution Settings</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Default Timeout (seconds)</label>
          <input v-model.number="localConfig.default_timeout" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Workers</label>
          <input v-model.number="localConfig.max_workers" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div class="flex items-center">
          <input v-model="localConfig.parallel" type="checkbox" id="parallel"
                 class="h-4 w-4 border rounded"
                 :class="theme ? ['text-indigo-600', 'focus:ring-indigo-500', theme.border] : 'text-indigo-600 focus:ring-indigo-500 border-gray-300'">
          <label for="parallel" class="ml-2 text-sm" :class="theme ? theme.text : 'text-gray-700'">Enable Parallel Execution</label>
        </div>
        <div class="flex items-center">
          <input v-model="localConfig.allow_shell" type="checkbox" id="allow_shell"
                 class="h-4 w-4 border rounded"
                 :class="theme ? ['text-indigo-600', 'focus:ring-indigo-500', theme.border] : 'text-indigo-600 focus:ring-indigo-500 border-gray-300'">
          <label for="allow_shell" class="ml-2 text-sm" :class="theme ? theme.text : 'text-gray-700'">Allow Shell Commands</label>
        </div>
      </div>
    </div>

    <!-- Retry Configuration -->
    <div class="rounded-lg shadow-sm border p-6 mb-6" :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
      <h3 class="text-lg font-semibold mb-4" :class="theme ? theme.text : 'text-gray-900'">Default Retry Configuration</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retries</label>
          <input v-model.number="localConfig.default_max_retries" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Delay (seconds)</label>
          <input v-model.number="localConfig.default_retry_delay" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Backoff</label>
          <input v-model.number="localConfig.default_retry_backoff" type="number" step="0.1"
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Retry Jitter</label>
          <input v-model.number="localConfig.default_retry_jitter" type="number" step="0.1"
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Max Retry Time (seconds)</label>
          <input v-model.number="localConfig.default_max_retry_time" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Default Retry Exit Codes</label>
          <input v-model="defaultRetryExitCodes" type="text" placeholder="1,2,3"
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
      </div>
    </div>

    <!-- Email Configuration -->
    <div class="rounded-lg shadow-sm border p-6 mb-6" :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
      <h3 class="text-lg font-semibold mb-4" :class="theme ? theme.text : 'text-gray-900'">Email Notifications</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Email Address</label>
          <input v-model="localConfig.email_address" type="email" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">SMTP Server</label>
          <input v-model="localConfig.smtp_server" type="text" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">SMTP Port</label>
          <input v-model.number="localConfig.smtp_port" type="number" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">SMTP User</label>
          <input v-model="localConfig.smtp_user" type="text" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">SMTP Password</label>
          <input v-model="localConfig.smtp_password" type="password" 
                 class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                 :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
        </div>
        <div class="flex items-center">
          <input v-model="localConfig.email_on_success" type="checkbox" id="email_on_success"
                 class="h-4 w-4 border rounded"
                 :class="theme ? ['text-indigo-600', 'focus:ring-indigo-500', theme.border] : 'text-indigo-600 focus:ring-indigo-500 border-gray-300'">
          <label for="email_on_success" class="ml-2 text-sm" :class="theme ? theme.text : 'text-gray-700'">Email on Success</label>
        </div>
        <div class="flex items-center">
          <input v-model="localConfig.email_on_failure" type="checkbox" id="email_on_failure"
                 class="h-4 w-4 border rounded"
                 :class="theme ? ['text-indigo-600', 'focus:ring-indigo-500', theme.border] : 'text-indigo-600 focus:ring-indigo-500 border-gray-300'">
          <label for="email_on_failure" class="ml-2 text-sm" :class="theme ? theme.text : 'text-gray-700'">Email on Failure</label>
        </div>
      </div>
    </div>

    <!-- Advanced Settings -->
    <div class="rounded-lg shadow-sm border p-6" :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
      <h3 class="text-lg font-semibold mb-4" :class="theme ? theme.text : 'text-gray-900'">Advanced Settings</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Environment Inheritance</label>
          <select v-model="localConfig.inherit_shell_env" 
                  class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                  :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <option value="default">Default</option>
            <option value="true">All</option>
            <option value="false">None</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1" :class="theme ? theme.text : 'text-gray-700'">Security Policy</label>
          <select v-model="localConfig.security_policy" 
                  class="w-full px-3 py-2 border rounded-lg focus:ring-2"
                  :class="theme ? [theme.surface, theme.border, theme.text, theme.focusRing] : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'">
            <option value="warn">Warn</option>
            <option value="strict">Strict</option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ApplicationConfig',
  props: {
    modelValue: {
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
      localConfig: JSON.parse(JSON.stringify(this.modelValue))
    };
  },
  computed: {
    defaultRetryExitCodes: {
      get() {
        return (this.localConfig.default_retry_on_exit_codes || []).join(',');
      },
      set(value) {
        this.localConfig.default_retry_on_exit_codes = value.split(',').map(v => parseInt(v.trim())).filter(v => !isNaN(v));
      }
    }
  },
  watch: {
    localConfig: {
      handler(newVal) {
        this.$emit('update:modelValue', newVal);
      },
      deep: true
    },
    modelValue: {
      handler(newVal) {
        this.localConfig = JSON.parse(JSON.stringify(newVal));
      },
      deep: true
    }
  }
};
</script>