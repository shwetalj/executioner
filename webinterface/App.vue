<template>
  <div class="min-h-screen" :class="theme.canvasBg">
    <!-- Header -->
    <header class="shadow-sm border-b" :class="[theme.headerBg, theme.border]">
      <div class="px-6 py-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-4">
            <h1 class="text-2xl font-bold" :class="theme.headerText">Executioner Workflow Editor</h1>
            <div v-if="currentFileName || appConfig.application_name" class="flex items-center space-x-3">
              <span :class="theme.headerTextMuted">|</span>
              <div class="flex flex-col">
                <span class="text-lg font-semibold" :class="theme.headerText">
                  {{ currentFileName || appConfig.application_name }}
                  <span v-if="isModified" class="text-sm text-orange-500">●</span>
                </span>
                <span class="text-xs" :class="theme.headerTextMuted" :title="currentFilePath ? `File: ${currentFilePath}` : 'In-memory configuration'">
                  <i class="fas fa-file-code mr-1"></i>
                  {{ currentFilePath || 'New Configuration' }}
                </span>
              </div>
            </div>
          </div>
          <div class="flex items-center space-x-4">
            <!-- Theme Selector -->
            <div class="relative">
              <button @click="showThemeMenu = !showThemeMenu" 
                      class="px-3 py-2 rounded-lg transition-colors flex items-center space-x-2"
                      :class="theme ? [theme.surface, theme.surfaceHover, theme.border, 'border'] : 'bg-white hover:bg-gray-50 border-gray-200 border'">
                <i class="fas fa-palette" :class="theme ? theme.text : ''"></i>
                <span class="text-sm" :class="theme ? theme.text : ''">{{ theme ? theme.name : 'Light' }}</span>
                <i class="fas fa-chevron-down text-xs" :class="theme ? theme.textMuted : ''"></i>
              </button>
              <div v-if="showThemeMenu" 
                   class="absolute right-0 mt-2 w-48 rounded-lg shadow-lg z-50 border"
                   :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
                <button v-for="(themeOption, key) in themes" :key="key"
                        @click="selectTheme(key)"
                        class="w-full px-4 py-2 text-left text-sm transition-colors"
                        :class="theme ? [theme.surfaceHover, theme.text, key === currentTheme ? 'bg-indigo-600 text-white' : ''] : 'hover:bg-gray-50 text-gray-900'">
                  {{ themeOption.name }}
                </button>
              </div>
            </div>
            
            <!-- Undo/Redo buttons -->
            <div class="flex items-center space-x-1 border-r pr-4 mr-2">
              <button @click="undo" :disabled="historyIndex <= 0" 
                      :class="['p-2 rounded transition-colors', historyIndex > 0 ? theme.surfaceHover + ' ' + theme.text : theme.textMuted + ' cursor-not-allowed']"
                      title="Undo (Ctrl+Z)">
                <i class="fas fa-undo"></i>
              </button>
              <button @click="redo" :disabled="historyIndex >= history.length - 1"
                      :class="['p-2 rounded transition-colors', historyIndex < history.length - 1 ? theme.surfaceHover + ' ' + theme.text : theme.textMuted + ' cursor-not-allowed']"
                      title="Redo (Ctrl+Shift+Z)">
                <i class="fas fa-redo"></i>
              </button>
            </div>
            
            <button @click="newConfig" class="px-4 py-2 border rounded-lg transition-colors" :class="[theme.surface, theme.border, theme.surfaceHover, theme.text]">
              <i class="fas fa-file-plus mr-2"></i>New Config
            </button>
            <button @click="loadConfig" class="px-4 py-2 border rounded-lg transition-colors" :class="[theme.surface, theme.border, theme.surfaceHover, theme.text]">
              <i class="fas fa-folder-open mr-2"></i>Load Config
            </button>
            <button @click="saveConfig" class="px-4 py-2 rounded-lg transition-colors" :class="[theme.accent, theme.accentText, theme.accentHover]"
                    title="Save (Ctrl+S)">
              <i class="fas fa-save mr-2"></i>Save Config
            </button>
          </div>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex flex-1" style="height: calc(100vh - 73px);">
      <!-- Left Sidebar - Jobs List -->
      <aside class="w-64 border-r overflow-y-auto" :class="[theme.sidebarBg, theme.border]">
        <!-- Application Config Section -->
        <div class="p-6 border-b" :class="theme.border">
          <button @click="showConfigModal = true" class="w-full text-left transition-colors" :class="[theme.text, 'hover:text-indigo-600']">
            <h2 class="text-lg font-semibold" :class="theme.text">
              <i class="fas fa-cog mr-2"></i>Application Config
            </h2>
          </button>
        </div>
        
        <!-- Jobs Section -->
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold" :class="theme.text">Jobs</h2>
            <button @click="addNewJob" class="px-3 py-1 text-sm rounded-lg transition-colors" :class="[theme.accent, theme.accentText, theme.accentHover]">
              <i class="fas fa-plus mr-1"></i>Add Job
            </button>
          </div>
          
          <!-- Jobs List -->
          <div class="space-y-2">
            <div v-for="job in jobs" :key="job.id"
                 class="p-2 rounded-lg border cursor-move transition-all"
                 :class="[theme.surface, theme.border, theme.nodeHover]"
                 draggable="true"
                 @dragstart="startDrag($event, job)"
                 @click="selectJob(job)">
              <div class="flex items-center justify-between">
                <h3 class="font-medium" :class="theme.text">{{ job.id }}</h3>
                <button @click.stop="removeJob(job.id)" class="text-red-500 hover:text-red-700">
                  <i class="fas fa-trash"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Main Content Area -->
      <main class="flex-1 flex flex-col h-full">
        <!-- Tabs -->
        <div class="border-b" :class="[theme.surface, theme.border]">
          <div class="flex">
            <button @click="activeTab = 'visual'" 
                    :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'visual' ? 'text-indigo-600 border-b-2 border-indigo-600' : theme.textMuted + ' ' + theme.surfaceHover]">
              <i class="fas fa-project-diagram mr-2"></i>Visual Editor
            </button>
            <button @click="activeTab = 'json'" 
                    :class="['px-6 py-3 text-sm font-medium transition-colors', activeTab === 'json' ? 'text-indigo-600 border-b-2 border-indigo-600' : theme.textMuted + ' ' + theme.surfaceHover]">
              <i class="fas fa-code mr-2"></i>JSON Editor
            </button>
          </div>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-hidden">
          <!-- Visual Editor Tab -->
          <div v-show="activeTab === 'visual'" class="h-full">
            <WorkflowCanvas :jobs="canvasJobs" :connections="connections" 
                           :theme="theme"
                           @update-positions="updateJobPositions"
                           @add-connection="addConnection"
                           @remove-connection="removeConnection"
                           @drop="handleDrop"
                           @select-job="selectJobById"
                           @clear-canvas="clearCanvas" />
          </div>

          <!-- JSON Editor Tab -->
          <div v-show="activeTab === 'json'" class="h-full">
            <JsonEditor v-model="configJson" :theme="theme" @update="updateFromJson" />
          </div>
        </div>
      </main>

      <!-- Right Sidebar - Job Editor -->
      <aside v-if="selectedJob && activeTab === 'visual'" class="w-96 border-l overflow-y-auto" :class="[theme.surface, theme.border]">
        <JobEditor :job="selectedJob" :theme="theme" @update="updateJob" @close="selectedJob = null" />
      </aside>
    </div>
    
    <!-- Application Config Modal -->
    <div v-if="showConfigModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click.self="showConfigModal = false">
      <div class="rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col" :class="theme.surface">
        <div class="px-6 py-4 border-b flex items-center justify-between" :class="theme.border">
          <h2 class="text-xl font-semibold" :class="theme.text">Application Configuration</h2>
          <button @click="showConfigModal = false" class="transition-colors" :class="[theme.textMuted, 'hover:' + theme.text]">
            <i class="fas fa-times text-xl"></i>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto">
          <ApplicationConfig v-model="appConfig" :theme="theme" />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import WorkflowCanvas from './components/WorkflowCanvas.vue';
import ApplicationConfig from './components/ApplicationConfig.vue';
import JsonEditor from './components/JsonEditor.vue';
import JobEditor from './components/JobEditor.vue';

export default {
  name: 'App',
  components: {
    WorkflowCanvas,
    ApplicationConfig,
    JsonEditor,
    JobEditor
  },
  data() {
    return {
      activeTab: 'visual',
      jobs: [],
      canvasJobs: [],
      connections: [],
      selectedJob: null,
      showConfigModal: false,
      currentFileName: null,
      currentFilePath: null,
      isModified: false,
      appConfig: {
        application_name: '',
        default_timeout: 10800,
        default_max_retries: 2,
        default_retry_delay: 30,
        default_retry_backoff: 1.5,
        default_retry_jitter: 0.1,
        default_max_retry_time: 1800,
        default_retry_on_exit_codes: [1],
        email_address: '',
        email_on_success: true,
        email_on_failure: true,
        smtp_server: '',
        smtp_port: 587,
        smtp_user: '',
        smtp_password: '',
        parallel: true,
        max_workers: 3,
        allow_shell: true,
        inherit_shell_env: 'default',
        env_variables: {},
        dependency_plugins: [],
        security_policy: 'warn',
        log_dir: './logs'
      },
      draggedJob: null,
      history: [],
      historyIndex: -1,
      maxHistorySize: 50,
      skipHistorySave: false,
      historyDebounceTimer: null,
      isInitialized: false,
      currentTheme: 'light',
      showThemeMenu: false,
      themes: {
        light: {
          name: 'Light',
          primary: 'bg-white',
          secondary: 'bg-gray-50',
          surface: 'bg-white',
          surfaceHover: 'hover:bg-gray-50',
          border: 'border-gray-200',
          text: 'text-gray-900',
          textMuted: 'text-gray-500',
          accent: 'bg-indigo-600',
          accentHover: 'hover:bg-indigo-700',
          accentText: 'text-white',
          headerBg: 'bg-white',
          headerText: 'text-gray-900',
          headerTextMuted: 'text-gray-500',
          sidebarBg: 'bg-white',
          canvasBg: 'bg-gray-50',
          nodeBg: 'bg-white',
          nodeHover: 'hover:border-indigo-300',
          nodeSelected: 'border-indigo-500 shadow-lg ring-2 ring-indigo-200',
          focusRing: 'focus:ring-indigo-500 focus:border-indigo-500'
        },
        dark: {
          name: 'Dark',
          primary: 'bg-gray-900',
          secondary: 'bg-gray-800',
          surface: 'bg-gray-800',
          surfaceHover: 'hover:bg-gray-700',
          border: 'border-gray-700',
          text: 'text-gray-100',
          textMuted: 'text-gray-400',
          accent: 'bg-indigo-600',
          accentHover: 'hover:bg-indigo-700',
          accentText: 'text-white',
          headerBg: 'bg-gray-900',
          headerText: 'text-gray-100',
          headerTextMuted: 'text-gray-400',
          sidebarBg: 'bg-gray-800',
          canvasBg: 'bg-gray-900',
          nodeBg: 'bg-gray-700',
          nodeHover: 'hover:border-indigo-400',
          nodeSelected: 'border-indigo-500 shadow-lg ring-2 ring-indigo-300',
          focusRing: 'focus:ring-indigo-400 focus:border-indigo-400'
        },
        midnight: {
          name: 'Midnight',
          primary: 'bg-gray-900',
          secondary: 'bg-gray-800',
          surface: 'bg-gray-800',
          surfaceHover: 'hover:bg-gray-700',
          border: 'border-gray-700',
          text: 'text-gray-100',
          textMuted: 'text-gray-400',
          accent: 'bg-purple-600',
          accentHover: 'hover:bg-purple-700',
          accentText: 'text-white',
          headerBg: 'bg-gray-900',
          headerText: 'text-gray-100',
          headerTextMuted: 'text-gray-400',
          sidebarBg: 'bg-gray-800',
          canvasBg: 'bg-gray-900',
          nodeBg: 'bg-gray-700',
          nodeHover: 'hover:border-purple-400',
          nodeSelected: 'border-purple-500 shadow-lg ring-2 ring-purple-300',
          focusRing: 'focus:ring-purple-400 focus:border-purple-400'
        },
        ocean: {
          name: 'Ocean',
          primary: 'bg-blue-50',
          secondary: 'bg-blue-100',
          surface: 'bg-white',
          surfaceHover: 'hover:bg-blue-50',
          border: 'border-blue-200',
          text: 'text-blue-900',
          textMuted: 'text-blue-600',
          accent: 'bg-blue-600',
          accentHover: 'hover:bg-blue-700',
          accentText: 'text-white',
          headerBg: 'bg-white',
          headerText: 'text-blue-900',
          headerTextMuted: 'text-blue-600',
          sidebarBg: 'bg-blue-50',
          canvasBg: 'bg-blue-50',
          nodeBg: 'bg-white',
          nodeHover: 'hover:border-blue-400',
          nodeSelected: 'border-blue-500 shadow-lg ring-2 ring-blue-200',
          focusRing: 'focus:ring-blue-500 focus:border-blue-500'
        },
        forest: {
          name: 'Forest',
          primary: 'bg-green-50',
          secondary: 'bg-green-100',
          surface: 'bg-white',
          surfaceHover: 'hover:bg-green-50',
          border: 'border-green-300',
          text: 'text-green-900',
          textMuted: 'text-green-700',
          accent: 'bg-emerald-600',
          accentHover: 'hover:bg-emerald-700',
          accentText: 'text-white',
          headerBg: 'bg-white',
          headerText: 'text-green-900',
          headerTextMuted: 'text-green-700',
          sidebarBg: 'bg-green-50',
          canvasBg: 'bg-green-50',
          nodeBg: 'bg-white',
          nodeHover: 'hover:border-emerald-400',
          nodeSelected: 'border-emerald-500 shadow-lg ring-2 ring-emerald-200',
          focusRing: 'focus:ring-emerald-500 focus:border-emerald-500'
        }
      }
    };
  },
  computed: {
    configJson() {
      const config = {
        ...this.appConfig,
        jobs: this.jobs
      };
      return JSON.stringify(config, null, 2);
    },
    theme() {
      return this.themes && this.themes[this.currentTheme] ? this.themes[this.currentTheme] : {
        name: 'Light',
        primary: 'bg-white',
        secondary: 'bg-gray-50',
        surface: 'bg-white',
        surfaceHover: 'hover:bg-gray-50',
        border: 'border-gray-200',
        text: 'text-gray-900',
        textMuted: 'text-gray-500',
        accent: 'bg-indigo-600',
        accentHover: 'hover:bg-indigo-700',
        accentText: 'text-white',
        headerBg: 'bg-white',
        sidebarBg: 'bg-white',
        canvasBg: 'bg-gray-50',
        nodeBg: 'bg-white',
        nodeHover: 'hover:border-indigo-300',
        nodeSelected: 'border-indigo-500 shadow-lg ring-2 ring-indigo-200'
      };
    }
  },
  watch: {
    jobs: {
      deep: true,
      handler() {
        if (!this.isInitialized || this.skipHistorySave) return;
        this.isModified = true;
        this.debouncedSaveToHistory();
      }
    },
    appConfig: {
      deep: true,
      handler() {
        if (!this.isInitialized || this.skipHistorySave) return;
        this.isModified = true;
        this.debouncedSaveToHistory();
      }
    },
    canvasJobs: {
      deep: true,
      handler() {
        if (!this.isInitialized || this.skipHistorySave) return;
        this.debouncedSaveToHistory();
      }
    },
    connections: {
      deep: true,
      handler() {
        if (!this.isInitialized || this.skipHistorySave) return;
        this.debouncedSaveToHistory();
      }
    }
  },
  methods: {
    newConfig() {
      if (confirm('Are you sure you want to create a new configuration? This will clear the current configuration.')) {
        this.jobs = [];
        this.canvasJobs = [];
        this.connections = [];
        this.selectedJob = null;
        this.currentFileName = null;
        this.currentFilePath = null;
        this.isModified = false;
        this.appConfig = {
          application_name: '',
          default_timeout: 10800,
          default_max_retries: 2,
          default_retry_delay: 30,
          default_retry_backoff: 1.5,
          default_retry_jitter: 0.1,
          default_max_retry_time: 1800,
          default_retry_on_exit_codes: [1],
          email_address: '',
          email_on_success: true,
          email_on_failure: true,
          smtp_server: '',
          smtp_port: 587,
          smtp_user: '',
          smtp_password: '',
          parallel: true,
          max_workers: 3,
          allow_shell: true,
          inherit_shell_env: 'default',
          env_variables: {},
          dependency_plugins: [],
          security_policy: 'warn',
          log_dir: './logs'
        };
      }
    },
    loadConfig() {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.json';
      input.onchange = (e) => {
        const file = e.target.files[0];
        if (file) {
          this.currentFileName = file.name.replace('.json', '');
          this.currentFilePath = file.name;
          const reader = new FileReader();
          reader.onload = (e) => {
            try {
              const config = JSON.parse(e.target.result);
              this.loadFromConfig(config);
              this.isModified = false;
            } catch (error) {
              alert('Invalid JSON file');
              this.currentFileName = null;
              this.currentFilePath = null;
            }
          };
          reader.readAsText(file);
        }
      };
      input.click();
    },
    saveConfig() {
      // Include canvas positions in saved jobs
      const jobsWithPositions = this.jobs.map(job => {
        const canvasJob = this.canvasJobs.find(cj => cj.id === job.id);
        if (canvasJob) {
          return {
            ...job,
            x: canvasJob.x,
            y: canvasJob.y
          };
        }
        return job;
      });
      
      const config = {
        ...this.appConfig,
        jobs: jobsWithPositions
      };
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${this.appConfig.application_name || 'config'}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.isModified = false;
      // Update the file path if saving for the first time
      if (!this.currentFilePath) {
        this.currentFilePath = a.download;
        this.currentFileName = a.download.replace('.json', '');
      }
    },
    loadFromConfig(config) {
      const { jobs, ...appConfig } = config;
      this.appConfig = { ...this.appConfig, ...appConfig };
      this.jobs = jobs || [];
      
      // Auto-layout jobs on canvas if they don't have positions
      this.canvasJobs = [];
      const jobsPerRow = 4;
      const horizontalSpacing = 180;
      const verticalSpacing = 100;
      const startX = 50;
      const startY = 50;
      
      this.jobs.forEach((job, index) => {
        const row = Math.floor(index / jobsPerRow);
        const col = index % jobsPerRow;
        
        this.canvasJobs.push({
          ...job,
          x: job.x || (startX + col * horizontalSpacing),
          y: job.y || (startY + row * verticalSpacing)
        });
      });
      
      this.connections = [];
      this.updateConnectionsFromJobs();
      
      // Save initial state to history
      this.$nextTick(() => {
        this.history = [];
        this.historyIndex = -1;
        this.saveToHistory();
      });
    },
    updateFromJson(jsonString) {
      try {
        const config = JSON.parse(jsonString);
        this.loadFromConfig(config);
      } catch (error) {
        console.error('Invalid JSON:', error);
      }
    },
    addNewJob() {
      // Generate a unique job ID
      let jobNumber = 1;
      let jobId = `job_${jobNumber}`;
      
      // Find the next available job number
      while (this.jobs.some(job => job.id === jobId)) {
        jobNumber++;
        jobId = `job_${jobNumber}`;
      }
      
      const newJob = {
        id: jobId,
        description: 'New Job',
        command: '',
        dependencies: [],
        timeout: this.appConfig.default_timeout,
        env_variables: {},
        pre_checks: [],
        post_checks: [],
        max_retries: this.appConfig.default_max_retries,
        retry_delay: this.appConfig.default_retry_delay,
        retry_backoff: this.appConfig.default_retry_backoff,
        retry_jitter: this.appConfig.default_retry_jitter,
        max_retry_time: this.appConfig.default_max_retry_time,
        retry_on_status: ['ERROR', 'FAILED', 'TIMEOUT'],
        retry_on_exit_codes: [...this.appConfig.default_retry_on_exit_codes]
      };
      this.jobs.push(newJob);
      this.selectedJob = newJob;
    },
    removeJob(jobId) {
      if (confirm('Are you sure you want to remove this job?')) {
        this.jobs = this.jobs.filter(job => job.id !== jobId);
        this.canvasJobs = this.canvasJobs.filter(job => job.id !== jobId);
        this.connections = this.connections.filter(conn => conn.from !== jobId && conn.to !== jobId);
        if (this.selectedJob?.id === jobId) {
          this.selectedJob = null;
        }
        // Update dependencies
        this.jobs.forEach(job => {
          if (job.dependencies) {
            job.dependencies = job.dependencies.filter(dep => dep !== jobId);
          }
        });
      }
    },
    selectJob(job) {
      this.selectedJob = job;
    },
    selectJobById(jobId) {
      const job = this.jobs.find(j => j.id === jobId);
      if (job) {
        this.selectedJob = job;
      }
    },
    updateJob(updatedJob) {
      const oldJob = this.jobs.find(job => job.id === this.selectedJob.id);
      const oldJobId = oldJob ? oldJob.id : null;
      const newJobId = updatedJob.id;
      
      // Check if new job ID already exists (and it's not the same job)
      if (oldJobId !== newJobId && this.jobs.some(job => job.id === newJobId)) {
        alert(`Job ID "${newJobId}" already exists. Please choose a different ID.`);
        // Revert the change in the editor
        this.$nextTick(() => {
          if (this.selectedJob) {
            this.selectedJob.id = oldJobId;
          }
        });
        return;
      }
      
      const index = this.jobs.findIndex(job => job.id === oldJobId);
      if (index !== -1) {
        // Update the job
        this.jobs[index] = updatedJob;
        
        // If job ID changed, update all references
        if (oldJobId !== newJobId) {
          // Update connections
          this.connections = this.connections.map(conn => ({
            from: conn.from === oldJobId ? newJobId : conn.from,
            to: conn.to === oldJobId ? newJobId : conn.to
          }));
          
          // Update dependencies in other jobs
          this.jobs.forEach(job => {
            if (job.dependencies && job.dependencies.includes(oldJobId)) {
              job.dependencies = job.dependencies.map(dep => 
                dep === oldJobId ? newJobId : dep
              );
            }
          });
          
          // Update canvas job if it exists
          const canvasJob = this.canvasJobs.find(job => job.id === oldJobId);
          if (canvasJob) {
            canvasJob.id = newJobId;
          }
        }
        
        // Update canvas job properties
        const canvasIndex = this.canvasJobs.findIndex(job => job.id === newJobId);
        if (canvasIndex !== -1) {
          this.canvasJobs[canvasIndex] = { ...this.canvasJobs[canvasIndex], ...updatedJob };
        }
        
        // Update selectedJob reference
        this.selectedJob = updatedJob;
        
        this.updateConnectionsFromJobs();
      }
    },
    startDrag(event, job) {
      this.draggedJob = job;
      event.dataTransfer.effectAllowed = 'copy';
    },
    handleDrop(event) {
      if (this.draggedJob) {
        const canvas = event.target.closest('.drop-zone');
        if (canvas) {
          const rect = canvas.getBoundingClientRect();
          const x = event.clientX - rect.left;
          const y = event.clientY - rect.top;
          
          // Check if job already exists on canvas
          const existingIndex = this.canvasJobs.findIndex(j => j.id === this.draggedJob.id);
          if (existingIndex === -1) {
            this.canvasJobs.push({
              ...this.draggedJob,
              x: x - 75, // Center the node
              y: y - 30
            });
          }
        }
        this.draggedJob = null;
      }
    },
    updateJobPositions(positions) {
      positions.forEach(pos => {
        const job = this.canvasJobs.find(j => j.id === pos.id);
        if (job) {
          job.x = pos.x;
          job.y = pos.y;
        }
      });
      
      // Save after drag operations complete
      clearTimeout(this.historyDebounceTimer);
      this.historyDebounceTimer = setTimeout(() => {
        this.saveToHistory();
      }, 500); // Shorter delay for position updates
    },
    addConnection(connection) {
      const existingIndex = this.connections.findIndex(
        conn => conn.from === connection.from && conn.to === connection.to
      );
      if (existingIndex === -1) {
        this.connections.push(connection);
        // Update job dependencies
        const toJob = this.jobs.find(job => job.id === connection.to);
        if (toJob) {
          if (!toJob.dependencies) {
            toJob.dependencies = [];
          }
          if (!toJob.dependencies.includes(connection.from)) {
            toJob.dependencies.push(connection.from);
          }
        }
      }
    },
    removeConnection(connection) {
      this.connections = this.connections.filter(
        conn => !(conn.from === connection.from && conn.to === connection.to)
      );
      // Update job dependencies
      const toJob = this.jobs.find(job => job.id === connection.to);
      if (toJob && toJob.dependencies) {
        toJob.dependencies = toJob.dependencies.filter(dep => dep !== connection.from);
      }
    },
    updateConnectionsFromJobs() {
      this.connections = [];
      if (!this.jobs) return;
      
      this.jobs.forEach(job => {
        if (job.dependencies && job.dependencies.length > 0) {
          job.dependencies.forEach(dep => {
            this.connections.push({ from: dep, to: job.id });
          });
        }
      });
    },
    clearCanvas() {
      this.canvasJobs = [];
      this.connections = [];
    },
    handleKeyDown(event) {
      // Save shortcut: Ctrl+S or Cmd+S
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        this.saveConfig();
      }
      // Undo shortcut: Ctrl+Z or Cmd+Z
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault();
        this.undo();
      }
      // Redo shortcut: Ctrl+Shift+Z or Cmd+Shift+Z (also support Ctrl+Y)
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        this.redo();
      }
      // Alternative redo shortcut: Ctrl+Y or Cmd+Y
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
        event.preventDefault();
        this.redo();
      }
    },
    debouncedSaveToHistory() {
      if (this.skipHistorySave) return;
      
      clearTimeout(this.historyDebounceTimer);
      this.historyDebounceTimer = setTimeout(() => {
        this.saveToHistory();
      }, 500); // Half second delay for reasonable grouping
    },
    saveToHistory() {
      if (this.skipHistorySave) {
        return;
      }
      
      // Create state snapshot
      const state = {
        jobs: JSON.parse(JSON.stringify(this.jobs || [])),
        canvasJobs: JSON.parse(JSON.stringify(this.canvasJobs || [])),
        connections: JSON.parse(JSON.stringify(this.connections || [])),
        appConfig: JSON.parse(JSON.stringify(this.appConfig || {}))
      };
      
      // Check if this state is actually different from the last one
      if (this.history.length > 0) {
        const lastState = this.history[this.historyIndex];
        if (JSON.stringify(state) === JSON.stringify(lastState)) {
          return; // Don't save duplicate states
        }
      }
      
      // Remove any states after current index (when we're in the middle of history)
      if (this.historyIndex < this.history.length - 1) {
        this.history = this.history.slice(0, this.historyIndex + 1);
      }
      
      // Add to history
      this.history.push(state);
      
      // Limit history size
      if (this.history.length > this.maxHistorySize) {
        this.history.shift();
      } else {
        this.historyIndex++;
      }
      
      // console.log('Saved to history. Length:', this.history.length, 'Index:', this.historyIndex);
    },
    undo() {
      if (this.historyIndex > 0) {
        this.historyIndex--;
        this.restoreFromHistory(this.history[this.historyIndex]);
      }
    },
    redo() {
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex++;
        this.restoreFromHistory(this.history[this.historyIndex]);
      }
    },
    restoreFromHistory(state) {
      // Temporarily disable watchers to prevent saving to history
      this.skipHistorySave = true;
      
      // Clear any pending history saves
      clearTimeout(this.historyDebounceTimer);
      
      this.jobs = JSON.parse(JSON.stringify(state.jobs));
      this.canvasJobs = JSON.parse(JSON.stringify(state.canvasJobs));
      this.connections = JSON.parse(JSON.stringify(state.connections));
      this.appConfig = JSON.parse(JSON.stringify(state.appConfig));
      
      // Re-enable after Vue has processed all updates
      this.$nextTick(() => {
        setTimeout(() => {
          this.skipHistorySave = false;
        }, 100);
      });
    },
    selectTheme(themeKey) {
      this.currentTheme = themeKey;
      this.showThemeMenu = false;
      // Save theme preference
      localStorage.setItem('selectedTheme', themeKey);
      // Close dropdown when clicking outside
      this.$nextTick(() => {
        document.addEventListener('click', this.closeThemeMenu);
      });
    },
    closeThemeMenu(event) {
      if (!event.target.closest('.relative')) {
        this.showThemeMenu = false;
        document.removeEventListener('click', this.closeThemeMenu);
      }
    }
  },
  mounted() {
    // Load saved theme
    const savedTheme = localStorage.getItem('selectedTheme');
    if (savedTheme && this.themes[savedTheme]) {
      this.currentTheme = savedTheme;
    }
    document.addEventListener('keydown', this.handleKeyDown);
    // Save initial empty state
    this.$nextTick(() => {
      this.isInitialized = true;
      this.saveToHistory();
    });
  },
  beforeUnmount() {
    document.removeEventListener('keydown', this.handleKeyDown);
  }
};
</script>