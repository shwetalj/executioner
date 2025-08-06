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
      <aside class="relative border-r overflow-y-auto flex-shrink-0" 
             :style="{ width: panelSizes.sidebar + 'px' }"
             :class="[theme.sidebarBg, theme.border]">
        <!-- Application Config Section -->
        <div class="p-6 border-b" :class="theme.border">
          <button @click="showConfigModal = true" class="w-full text-left transition-colors" :class="[theme.text, 'hover:text-indigo-600']">
            <h2 class="text-lg font-semibold" :class="theme.text">
              <i class="fas fa-cog mr-2"></i>Application Config
            </h2>
          </button>
        </div>
        
        <!-- Jobs Section -->
        <div class="p-6 relative" 
             @mousedown="startPointerSelection" 
             @mousemove="updatePointerSelection" 
             @mouseup="endPointerSelection"
             @mouseleave="endPointerSelection">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold" :class="theme.text">Jobs</h2>
            <button @click="addNewJob" class="px-3 py-1 text-sm rounded-lg transition-colors" :class="[theme.accent, theme.accentText, theme.accentHover]">
              <i class="fas fa-plus mr-1"></i>Add Job
            </button>
          </div>
          
          <!-- Multi-select hints -->
          <div class="text-xs mb-2 p-2 rounded" :class="[theme.secondary, theme.textMuted]">
            <div class="space-y-0.5">
              <div><i class="fas fa-mouse-pointer mr-1"></i>Drag to lasso select</div>
              <div><kbd class="px-1 py-0.5 text-xs rounded bg-gray-200 dark:bg-gray-700">Ctrl</kbd>+Click: Toggle selection</div>
              <div><kbd class="px-1 py-0.5 text-xs rounded bg-gray-200 dark:bg-gray-700">Shift</kbd>+Click: Select range</div>
              <div><kbd class="px-1 py-0.5 text-xs rounded bg-gray-200 dark:bg-gray-700">F2</kbd>: Rename selected</div>
            </div>
          </div>
          
          <!-- Jobs List -->
          <div class="space-y-1">
            <div v-for="job in jobs" :key="job.id"
                 :ref="`job-${job.id}`"
                 class="group p-2 rounded border cursor-pointer select-none transition-all relative job-item"
                 :class="[
                   theme.surface, 
                   theme.border, 
                   isJobSelected(job.id) ? theme.nodeSelected : theme.nodeHover,
                   'hover:shadow-sm'
                 ]"
                 :title="job.description || job.id"
                 :data-job-id="job.id"
                 draggable="true"
                 @dragstart="startDrag($event, job)"
                 @click="handleJobClick(job, $event)"
                 @dblclick="selectJobAndEdit(job)"
                 @contextmenu.prevent="showContextMenu($event, job)">
              <div class="flex items-center justify-between">
                <div class="flex items-center space-x-2 flex-1">
                  <i v-if="isJobSelected(job.id)" class="fas fa-check-circle text-green-500 text-sm"></i>
                  <div v-if="renamingJobId === job.id" class="flex-1">
                    <input type="text" 
                           v-model="renamingJobNewName"
                           @keyup.enter="confirmRename"
                           @keyup.esc="cancelRename"
                           @blur="confirmRename"
                           @click.stop
                           class="w-full px-1 py-0 text-sm border rounded"
                           :class="[theme.border, theme.text, theme.surface]"
                           ref="renameInput"
                           autofocus />
                  </div>
                  <h3 v-else class="font-medium text-sm" :class="theme.text">{{ job.id }}</h3>
                  <i v-if="job.description && renamingJobId !== job.id" class="fas fa-info-circle text-xs" :class="theme.textMuted"></i>
                </div>
                <button @click.stop="removeJob(job.id)" 
                        class="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 transition-opacity">
                  <i class="fas fa-trash text-sm"></i>
                </button>
              </div>
            </div>
          </div>
          
          <!-- Pointer Selection Overlay -->
          <div v-if="isPointerSelecting" 
               class="absolute border-2 border-blue-500 bg-blue-500 bg-opacity-10 pointer-events-none"
               :style="{
                 left: Math.min(pointerSelection.startX, pointerSelection.endX) + 'px',
                 top: Math.min(pointerSelection.startY, pointerSelection.endY) + 'px',
                 width: Math.abs(pointerSelection.endX - pointerSelection.startX) + 'px',
                 height: Math.abs(pointerSelection.endY - pointerSelection.startY) + 'px'
               }">
          </div>
        </div>
      </aside>
      
      <!-- Sidebar Resize Handle -->
      <div class="relative w-1 cursor-col-resize hover:bg-blue-500 transition-colors group"
           :class="isResizing.sidebar ? 'bg-blue-500' : 'bg-transparent'"
           @mousedown="startResizeSidebar">
        <div class="absolute inset-y-0 -left-1 -right-1 group-hover:bg-blue-500 group-hover:opacity-20"></div>
      </div>

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
                           @clear-canvas="clearCanvas"
                           @delete-nodes="deleteCanvasNodes"
                           @paste-nodes="pasteCanvasNodes"
                           @duplicate-nodes="duplicateCanvasNodes"
                           @rename-node="renameCanvasNode"
                           @edit-node="editCanvasNode"
                           @delete-connection="deleteConnection"
                           @edit-connection="editConnection" />
          </div>

          <!-- JSON Editor Tab -->
          <div v-show="activeTab === 'json'" class="h-full">
            <JsonEditor v-model="configJson" :theme="theme" @update="updateFromJson" />
          </div>
        </div>
      </main>

      <!-- Job Editor Resize Handle -->
      <div v-if="selectedJob && activeTab === 'visual'"
           class="relative w-1 cursor-col-resize hover:bg-blue-500 transition-colors group"
           :class="isResizing.jobEditor ? 'bg-blue-500' : 'bg-transparent'"
           @mousedown="startResizeJobEditor">
        <div class="absolute inset-y-0 -left-1 -right-1 group-hover:bg-blue-500 group-hover:opacity-20"></div>
      </div>
      
      <!-- Right Sidebar - Job Editor -->
      <aside v-if="selectedJob && activeTab === 'visual'" 
             class="border-l overflow-y-auto flex-shrink-0" 
             :style="{ width: panelSizes.jobEditor + 'px' }"
             :class="[theme.surface, theme.border]">
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
  
  <!-- Context Menu -->
  <div v-if="contextMenu.visible" 
       class="fixed z-50 py-1 rounded-lg shadow-lg min-w-[150px]"
       :class="[theme.surface, theme.border]"
       :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
       @click.stop>
    <button v-if="contextMenu.targetJob" 
            @click="editJobFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-edit mr-2 w-4"></i>Edit
    </button>
    <button v-if="contextMenu.targetJob" 
            @click="renameJobFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-i-cursor mr-2 w-4"></i>Rename
    </button>
    <button v-if="contextMenu.targetJob && !isJobOnCanvas(contextMenu.targetJob.id)" 
            @click="addJobToCanvasFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-plus-circle mr-2 w-4"></i>Add to Canvas
    </button>
    <button v-if="contextMenu.targetJob" 
            @click="duplicateJobFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-copy mr-2 w-4"></i>Duplicate
    </button>
    <div class="border-t my-1" :class="theme.border"></div>
    <button @click="selectAllJobsFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-check-square mr-2 w-4"></i>Select All
    </button>
    <button v-if="selectedJobs.length > 0"
            @click="clearSelectionFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-times-circle mr-2 w-4"></i>Clear Selection
    </button>
    <div v-if="selectedJobs.length > 0" class="border-t my-1" :class="theme.border"></div>
    <button v-if="selectedJobs.length > 1"
            @click="addSelectedJobsToCanvasFromContext"
            class="w-full text-left px-4 py-2 text-sm transition-colors"
            :class="[theme.text, theme.surfaceHover]">
      <i class="fas fa-plus-square mr-2 w-4"></i>Add {{ selectedJobs.length }} Selected to Canvas
    </button>
    <button v-if="selectedJobs.length > 0"
            @click="deleteSelectedJobsFromContext"
            class="w-full text-left px-4 py-2 text-sm text-red-500 transition-colors"
            :class="theme.surfaceHover">
      <i class="fas fa-trash mr-2 w-4"></i>Delete {{ selectedJobs.length }} Selected
    </button>
    <button v-if="contextMenu.targetJob && selectedJobs.length === 0" 
            @click="deleteJobFromContext"
            class="w-full text-left px-4 py-2 text-sm text-red-500 transition-colors"
            :class="theme.surfaceHover">
      <i class="fas fa-trash mr-2 w-4"></i>Delete
    </button>
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
      selectedJobs: [], // Track multiple selected jobs
      editingJob: null, // Job being edited in modal
      showJobModal: false, // Show job edit modal
      isPointerSelecting: false,
      pointerSelection: {
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0
      },
      contextMenu: {
        visible: false,
        x: 0,
        y: 0,
        targetJob: null
      },
      // Panel resizing
      panelSizes: {
        sidebar: 256, // 16rem = 256px (w-64)
        jobEditor: 384 // 24rem = 384px (w-96)
      },
      isResizing: {
        sidebar: false,
        jobEditor: false
      },
      // Rename functionality
      renamingJobId: null,
      renamingJobNewName: '',
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
    // Multi-select methods
    isJobSelected(jobId) {
      return this.selectedJobs.includes(jobId);
    },
    handleJobClick(job, event) {
      // Handle keyboard modifiers for multi-select
      if (event.shiftKey && this.selectedJobs.length > 0) {
        // Shift+Click: Select range
        event.preventDefault();
        this.selectJobRange(job);
      } else if (event.ctrlKey || event.metaKey) {
        // Ctrl/Cmd+Click: Toggle individual selection
        event.preventDefault();
        const index = this.selectedJobs.indexOf(job.id);
        if (index > -1) {
          this.selectedJobs.splice(index, 1);
        } else {
          this.selectedJobs.push(job.id);
        }
      } else {
        // Regular click: Select single job and show in editor
        this.selectedJobs = [];
        this.selectJob(job);
      }
    },
    selectJobAndEdit(job) {
      // Double-click: Select and edit job
      this.selectedJobs = [];
      this.selectJob(job);
    },
    selectJobRange(toJob) {
      const lastSelectedId = this.selectedJobs[this.selectedJobs.length - 1];
      const fromIndex = this.jobs.findIndex(j => j.id === lastSelectedId);
      const toIndex = this.jobs.findIndex(j => j.id === toJob.id);
      
      if (fromIndex !== -1 && toIndex !== -1) {
        const start = Math.min(fromIndex, toIndex);
        const end = Math.max(fromIndex, toIndex);
        
        for (let i = start; i <= end; i++) {
          if (!this.selectedJobs.includes(this.jobs[i].id)) {
            this.selectedJobs.push(this.jobs[i].id);
          }
        }
      }
    },
    clearSelection() {
      this.selectedJobs = [];
    },
    selectAllJobs() {
      this.selectedJobs = this.jobs.map(job => job.id);
    },
    // Pointer Selection Methods
    startPointerSelection(event) {
      // Only start lasso if dragging from empty space (not on a job)
      if (event.target.closest('.job-item')) return;
      
      const container = event.currentTarget;
      const rect = container.getBoundingClientRect();
      
      this.isPointerSelecting = true;
      this.pointerSelection.startX = event.clientX - rect.left;
      this.pointerSelection.startY = event.clientY - rect.top;
      this.pointerSelection.endX = this.pointerSelection.startX;
      this.pointerSelection.endY = this.pointerSelection.startY;
      this.pointerSelection.ctrlKey = event.ctrlKey || event.metaKey;
      
      // Clear previous selection unless Ctrl/Cmd is held
      if (!event.ctrlKey && !event.metaKey) {
        this.selectedJobs = [];
      }
    },
    updatePointerSelection(event) {
      if (!this.isPointerSelecting) return;
      
      const container = event.currentTarget;
      const rect = container.getBoundingClientRect();
      
      this.pointerSelection.endX = event.clientX - rect.left;
      this.pointerSelection.endY = event.clientY - rect.top;
      
      // Check which jobs are within the selection area
      this.updateSelectedJobsInArea();
    },
    endPointerSelection() {
      this.isPointerSelecting = false;
    },
    updateSelectedJobsInArea() {
      const selectionRect = {
        left: Math.min(this.pointerSelection.startX, this.pointerSelection.endX),
        top: Math.min(this.pointerSelection.startY, this.pointerSelection.endY),
        right: Math.max(this.pointerSelection.startX, this.pointerSelection.endX),
        bottom: Math.max(this.pointerSelection.startY, this.pointerSelection.endY)
      };
      
      // Get the initial selection state (before this lasso)
      const initialSelection = [...this.selectedJobs];
      const lassoSelection = [];
      
      this.jobs.forEach(job => {
        const jobEl = this.$refs[`job-${job.id}`]?.[0];
        if (jobEl) {
          const jobRect = jobEl.getBoundingClientRect();
          const containerRect = jobEl.closest('.p-6').getBoundingClientRect();
          
          const jobRelativeRect = {
            left: jobRect.left - containerRect.left,
            top: jobRect.top - containerRect.top,
            right: jobRect.right - containerRect.left,
            bottom: jobRect.bottom - containerRect.top
          };
          
          // Check if job is within selection
          if (jobRelativeRect.left < selectionRect.right &&
              jobRelativeRect.right > selectionRect.left &&
              jobRelativeRect.top < selectionRect.bottom &&
              jobRelativeRect.bottom > selectionRect.top) {
            lassoSelection.push(job.id);
          }
        }
      });
      
      // Combine with existing selection if Ctrl/Cmd was held
      // Otherwise replace with new selection
      if (this.pointerSelection.ctrlKey) {
        // Add lasso selection to existing, avoiding duplicates
        this.selectedJobs = [...new Set([...initialSelection, ...lassoSelection])];
      } else {
        this.selectedJobs = lassoSelection;
      }
    },
    // Context Menu Methods
    showContextMenu(event, job) {
      this.contextMenu.targetJob = job;
      this.contextMenu.x = event.clientX;
      this.contextMenu.y = event.clientY;
      this.contextMenu.visible = true;
      
      // Add click listener to hide menu
      setTimeout(() => {
        document.addEventListener('click', this.hideContextMenu, { once: true });
      }, 0);
    },
    hideContextMenu() {
      this.contextMenu.visible = false;
      this.contextMenu.targetJob = null;
    },
    isJobOnCanvas(jobId) {
      return this.canvasJobs.some(j => j.id === jobId);
    },
    editJobFromContext() {
      if (this.contextMenu.targetJob) {
        this.selectJob(this.contextMenu.targetJob);
        this.hideContextMenu();
      }
    },
    addJobToCanvasFromContext() {
      if (this.contextMenu.targetJob && !this.isJobOnCanvas(this.contextMenu.targetJob.id)) {
        // Create a deep copy to avoid reference issues
        const jobCopy = JSON.parse(JSON.stringify(this.contextMenu.targetJob));
        this.canvasJobs.push({
          ...jobCopy,
          x: 150,
          y: 150
        });
        this.saveToHistory();
        this.hideContextMenu();
      }
    },
    duplicateJobFromContext() {
      if (this.contextMenu.targetJob) {
        // Create a deep copy of the job to avoid reference issues
        const timestamp = Date.now();
        const newJob = JSON.parse(JSON.stringify(this.contextMenu.targetJob));
        
        // Generate a unique ID
        newJob.id = `${this.contextMenu.targetJob.id}_copy_${timestamp}`;
        
        // Clear dependencies for the duplicated job
        // Duplicated jobs should start without dependencies to avoid confusion
        newJob.dependencies = [];
        
        this.jobs.push(newJob);
        this.saveToHistory();
        this.hideContextMenu();
      }
    },
    selectAllJobsFromContext() {
      this.selectAllJobs();
      this.hideContextMenu();
    },
    clearSelectionFromContext() {
      this.clearSelection();
      this.hideContextMenu();
    },
    addSelectedJobsToCanvasFromContext() {
      this.addSelectedJobsToCanvas();
      this.hideContextMenu();
    },
    deleteSelectedJobsFromContext() {
      this.deleteSelectedJobs();
      this.hideContextMenu();
    },
    deleteJobFromContext() {
      if (this.contextMenu.targetJob) {
        this.removeJob(this.contextMenu.targetJob.id);
        this.hideContextMenu();
      }
    },
    renameJobFromContext() {
      if (this.contextMenu.targetJob) {
        this.startRename(this.contextMenu.targetJob);
        this.hideContextMenu();
      }
    },
    startRename(job) {
      this.renamingJobId = job.id;
      this.renamingJobNewName = job.id;
      
      // Focus the input after Vue updates the DOM
      this.$nextTick(() => {
        const input = this.$refs.renameInput;
        if (input) {
          input.focus();
          input.select();
        }
      });
    },
    confirmRename() {
      if (!this.renamingJobId || !this.renamingJobNewName) {
        this.cancelRename();
        return;
      }
      
      const newName = this.renamingJobNewName.trim();
      
      // Validate new name
      if (!newName) {
        alert('Job name cannot be empty');
        this.cancelRename();
        return;
      }
      
      // Check for duplicate names
      const isDuplicate = this.jobs.some(j => j.id === newName && j.id !== this.renamingJobId);
      if (isDuplicate) {
        alert('A job with this name already exists');
        return;
      }
      
      // Find and update the job
      const job = this.jobs.find(j => j.id === this.renamingJobId);
      if (job) {
        const oldId = job.id;
        job.id = newName;
        
        // Update the job in canvasJobs if it exists there
        const canvasJob = this.canvasJobs.find(j => j.id === oldId);
        if (canvasJob) {
          canvasJob.id = newName;
        }
        
        // Update connections that reference this job
        this.connections.forEach(conn => {
          if (conn.from === oldId) conn.from = newName;
          if (conn.to === oldId) conn.to = newName;
        });
        
        // Update dependencies in all jobs
        this.jobs.forEach(j => {
          if (j.dependencies && Array.isArray(j.dependencies)) {
            const depIndex = j.dependencies.indexOf(oldId);
            if (depIndex > -1) {
              j.dependencies[depIndex] = newName;
            }
          }
        });
        
        // Update selected jobs
        const selectedIndex = this.selectedJobs.indexOf(oldId);
        if (selectedIndex > -1) {
          this.selectedJobs[selectedIndex] = newName;
        }
        
        // Update selectedJob if it's the renamed job
        if (this.selectedJob && this.selectedJob.id === oldId) {
          this.selectedJob.id = newName;
        }
        
        this.saveToHistory();
      }
      
      this.cancelRename();
    },
    cancelRename() {
      this.renamingJobId = null;
      this.renamingJobNewName = '';
    },
    // Panel Resizing Methods
    startResizeSidebar(event) {
      this.isResizing.sidebar = true;
      document.addEventListener('mousemove', this.resizeSidebar);
      document.addEventListener('mouseup', this.stopResizeSidebar);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      event.preventDefault();
    },
    resizeSidebar(event) {
      if (!this.isResizing.sidebar) return;
      
      const newWidth = event.clientX;
      const minWidth = 200;
      const maxWidth = 500;
      
      this.panelSizes.sidebar = Math.min(Math.max(newWidth, minWidth), maxWidth);
    },
    stopResizeSidebar() {
      this.isResizing.sidebar = false;
      document.removeEventListener('mousemove', this.resizeSidebar);
      document.removeEventListener('mouseup', this.stopResizeSidebar);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      
      // Save to localStorage
      this.savePanelSizes();
    },
    startResizeJobEditor(event) {
      this.isResizing.jobEditor = true;
      document.addEventListener('mousemove', this.resizeJobEditor);
      document.addEventListener('mouseup', this.stopResizeJobEditor);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      event.preventDefault();
    },
    resizeJobEditor(event) {
      if (!this.isResizing.jobEditor) return;
      
      const windowWidth = window.innerWidth;
      const newWidth = windowWidth - event.clientX;
      const minWidth = 300;
      const maxWidth = 600;
      
      this.panelSizes.jobEditor = Math.min(Math.max(newWidth, minWidth), maxWidth);
    },
    stopResizeJobEditor() {
      this.isResizing.jobEditor = false;
      document.removeEventListener('mousemove', this.resizeJobEditor);
      document.removeEventListener('mouseup', this.stopResizeJobEditor);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      
      // Save to localStorage
      this.savePanelSizes();
    },
    savePanelSizes() {
      localStorage.setItem('executioner-panel-sizes', JSON.stringify(this.panelSizes));
    },
    loadPanelSizes() {
      const saved = localStorage.getItem('executioner-panel-sizes');
      if (saved) {
        try {
          const sizes = JSON.parse(saved);
          this.panelSizes = { ...this.panelSizes, ...sizes };
        } catch (e) {
          console.error('Failed to load panel sizes:', e);
        }
      }
    },
    deleteSelectedJobs() {
      if (this.selectedJobs.length === 0) return;
      
      const count = this.selectedJobs.length;
      if (confirm(`Are you sure you want to delete ${count} job(s)?`)) {
        this.selectedJobs.forEach(jobId => {
          this.removeJob(jobId);
        });
        this.selectedJobs = [];
      }
    },
    addSelectedJobsToCanvas() {
      if (this.selectedJobs.length === 0) return;
      
      // Calculate starting position for the group
      const startX = 150;
      const startY = 150;
      const spacing = 150;
      
      this.selectedJobs.forEach((jobId, index) => {
        const job = this.jobs.find(j => j.id === jobId);
        if (job && !this.canvasJobs.find(cj => cj.id === job.id)) {
          // Add job to canvas with staggered positioning
          const row = Math.floor(index / 3);
          const col = index % 3;
          
          // Create a deep copy to avoid reference issues
          const jobCopy = JSON.parse(JSON.stringify(job));
          this.canvasJobs.push({
            ...jobCopy,
            x: startX + (col * spacing),
            y: startY + (row * spacing)
          });
        }
      });
      
      // Clear selection after adding
      this.selectedJobs = [];
      
      // Save to history
      this.saveToHistory();
    },
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
      
      // Initially add jobs to canvas (positions will be set by WorkflowCanvas auto-arrange)
      this.canvasJobs = [];
      
      this.jobs.forEach((job) => {
        this.canvasJobs.push({
          ...job,
          // Use saved positions if available, otherwise let auto-arrange handle it
          x: job.x || 0,
          y: job.y || 0
        });
      });
      
      this.connections = [];
      this.updateConnectionsFromJobs();
      
      // Save initial state to history
      // The WorkflowCanvas component will auto-arrange with layered layout
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
      // If dragging a selected job, drag all selected jobs
      if (this.selectedJobs.includes(job.id) && this.selectedJobs.length > 1) {
        this.draggedJob = {
          isMultiple: true,
          jobs: this.selectedJobs.map(id => this.jobs.find(j => j.id === id)).filter(j => j)
        };
      } else {
        this.draggedJob = job;
      }
      event.dataTransfer.effectAllowed = 'copy';
    },
    handleDrop(event, gridSettings = {}) {
      if (this.draggedJob) {
        const canvas = event.target.closest('.drop-zone');
        if (canvas) {
          const rect = canvas.getBoundingClientRect();
          let x = event.clientX - rect.left;
          let y = event.clientY - rect.top;
          
          // Apply snap to grid if enabled
          if (gridSettings.snapToGrid && gridSettings.gridSize) {
            x = Math.round(x / gridSettings.gridSize) * gridSettings.gridSize;
            y = Math.round(y / gridSettings.gridSize) * gridSettings.gridSize;
          }
          
          // Handle multiple jobs drop
          if (this.draggedJob.isMultiple) {
            const spacing = 150;
            this.draggedJob.jobs.forEach((job, index) => {
              if (!this.canvasJobs.find(cj => cj.id === job.id)) {
                const row = Math.floor(index / 3);
                const col = index % 3;
                
                // Create a deep copy to avoid reference issues
                const jobCopy = JSON.parse(JSON.stringify(job));
                this.canvasJobs.push({
                  ...jobCopy,
                  x: (x - 75) + (col * spacing),
                  y: (y - 30) + (row * spacing)
                });
              }
            });
            // Clear selection after dropping
            this.selectedJobs = [];
          } else {
            // Single job drop
            const existingIndex = this.canvasJobs.findIndex(j => j.id === this.draggedJob.id);
            if (existingIndex === -1) {
              // Create a deep copy to avoid reference issues
              const jobCopy = JSON.parse(JSON.stringify(this.draggedJob));
              this.canvasJobs.push({
                ...jobCopy,
                x: x - 75, // Center the node
                y: y - 30
              });
            }
          }
        }
        this.draggedJob = null;
      }
    },
    updateJobPositions(positions) {
      positions.forEach(pos => {
        // Update position in canvasJobs
        const canvasJob = this.canvasJobs.find(j => j.id === pos.id);
        if (canvasJob) {
          // Update the position properties directly
          canvasJob.x = pos.x;
          canvasJob.y = pos.y;
        }
        
        // Also update in main jobs array if it exists there
        const mainJob = this.jobs.find(j => j.id === pos.id);
        if (mainJob) {
          // Store canvas position in the main job for persistence
          mainJob.x = pos.x;
          mainJob.y = pos.y;
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
      if (!this.canvasJobs) return;
      
      // Only create connections for jobs that are on the canvas
      this.canvasJobs.forEach(canvasJob => {
        // Find the corresponding job in the main jobs array
        const job = this.jobs.find(j => j.id === canvasJob.id);
        if (job && job.dependencies && job.dependencies.length > 0) {
          job.dependencies.forEach(dep => {
            // Only add connection if the dependency is also on the canvas
            if (this.canvasJobs.find(cj => cj.id === dep)) {
              this.connections.push({ from: dep, to: job.id });
            }
          });
        }
      });
    },
    clearCanvas() {
      this.canvasJobs = [];
      this.connections = [];
    },
    deleteCanvasNodes(nodeIds) {
      // Remove nodes from canvas
      this.canvasJobs = this.canvasJobs.filter(job => !nodeIds.includes(job.id));
      
      // Remove connections involving these nodes
      this.connections = this.connections.filter(conn => 
        !nodeIds.includes(conn.from) && !nodeIds.includes(conn.to)
      );
      
      // Update dependencies in the main jobs array
      nodeIds.forEach(nodeId => {
        this.jobs.forEach(job => {
          if (job.dependencies && job.dependencies.includes(nodeId)) {
            job.dependencies = job.dependencies.filter(dep => dep !== nodeId);
          }
        });
      });
      
      this.saveToHistory();
    },
    pasteCanvasNodes(pasteData) {
      // Handle both old format (array) and new format (object with position)
      let nodes, pastePosition;
      if (Array.isArray(pasteData)) {
        // Old format - just an array of nodes
        nodes = pasteData;
        pastePosition = null;
      } else {
        // New format - object with nodes and position
        nodes = pasteData.nodes || [];
        pastePosition = pasteData.position || null;
      }
      
      // Generate new IDs and add nodes to canvas
      const timestamp = Date.now();
      const spacing = 30; // Spacing between pasted nodes
      
      nodes.forEach((node, index) => {
        const newNode = JSON.parse(JSON.stringify(node));
        newNode.id = `${node.id}_paste_${timestamp}_${index}`;
        
        // If we have a paste position (from context menu), use it
        if (pastePosition) {
          newNode.x = pastePosition.x + (index * spacing);
          newNode.y = pastePosition.y + (index * spacing);
        } else {
          // Otherwise offset from original position
          newNode.x = (node.x || 100) + spacing;
          newNode.y = (node.y || 100) + spacing;
        }
        
        newNode.dependencies = []; // Clear dependencies for pasted nodes
        
        // Add to main jobs list first
        const mainJob = {
          id: newNode.id,
          description: newNode.description || '',
          command: newNode.command || '',
          dependencies: [],
          timeout: newNode.timeout,
          env_variables: newNode.env_variables || {},
          pre_checks: newNode.pre_checks || [],
          post_checks: newNode.post_checks || [],
          x: newNode.x,
          y: newNode.y
        };
        
        if (!this.jobs.find(j => j.id === newNode.id)) {
          this.jobs.push(mainJob);
        }
        
        // Add to canvas
        this.canvasJobs.push({...mainJob});
      });
      
      this.saveToHistory();
    },
    duplicateCanvasNodes(nodes) {
      const timestamp = Date.now();
      const baseOffset = 30; // Base offset for duplicated nodes
      
      nodes.forEach((node, index) => {
        // Create unique offset for each node to avoid overlap
        const offset = baseOffset + (index * 10);
        
        // Generate unique ID
        const newId = `${node.id}_copy_${timestamp}_${index}`;
        
        // Create a new job object for the main jobs list with deep copy of properties
        const newMainJob = {
          id: newId,
          description: node.description || '',
          command: node.command || '',
          dependencies: [],
          timeout: node.timeout,
          env_variables: node.env_variables ? {...node.env_variables} : {},
          pre_checks: node.pre_checks ? [...node.pre_checks] : [],
          post_checks: node.post_checks ? [...node.post_checks] : [],
          x: (node.x || 100) + offset,
          y: (node.y || 100) + offset
        };
        
        // Add to main jobs list
        this.jobs.push(newMainJob);
        
        // Create canvas job - using spread to ensure it's a new object
        const newCanvasJob = {
          ...newMainJob
        };
        
        // Add to canvas
        this.canvasJobs.push(newCanvasJob);
      });
      
      this.saveToHistory();
    },
    renameCanvasNode({ node, newName }) {
      // Find and rename the node in both canvasJobs and jobs arrays
      const canvasJob = this.canvasJobs.find(j => j.id === node.id);
      const mainJob = this.jobs.find(j => j.id === node.id);
      
      if (canvasJob && mainJob) {
        // Store old name for updating dependencies
        const oldName = canvasJob.id;
        
        // Update the node ID
        canvasJob.id = newName;
        mainJob.id = newName;
        
        // Update all dependencies that reference the old name
        this.jobs.forEach(job => {
          if (job.dependencies && job.dependencies.includes(oldName)) {
            const index = job.dependencies.indexOf(oldName);
            job.dependencies[index] = newName;
          }
        });
        
        // Update connections
        this.connections.forEach(conn => {
          if (conn.from === oldName) conn.from = newName;
          if (conn.to === oldName) conn.to = newName;
        });
        
        this.saveToHistory();
      }
    },
    editCanvasNode(node) {
      // Find the job in the main jobs list
      const job = this.jobs.find(j => j.id === node.id);
      if (job) {
        // Open the job edit modal or panel
        this.editingJob = job;
        this.showJobModal = true;
      }
    },
    deleteConnection(connection) {
      // Remove the connection
      const index = this.connections.findIndex(c => 
        c.from === connection.from && c.to === connection.to
      );
      
      if (index !== -1) {
        this.connections.splice(index, 1);
        
        // Update the dependency in the target job
        const targetJob = this.jobs.find(j => j.id === connection.to);
        if (targetJob && targetJob.dependencies) {
          targetJob.dependencies = targetJob.dependencies.filter(dep => dep !== connection.from);
        }
        
        this.saveToHistory();
      }
    },
    editConnection(connection) {
      // For now, just log it. In the future, could open a modal to edit connection properties
      console.log('Edit connection:', connection);
      // Future implementation: Open modal to edit connection properties like conditions, etc.
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
      // Rename shortcut: F2
      if (event.key === 'F2' && this.selectedJob && !this.renamingJobId) {
        event.preventDefault();
        this.startRename(this.selectedJob);
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
    
    // Load saved panel sizes
    this.loadPanelSizes();
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

<style scoped>

/* Context menu animation */
.context-menu-enter-active,
.context-menu-leave-active {
  transition: opacity 0.1s ease;
}

.context-menu-enter-from,
.context-menu-leave-to {
  opacity: 0;
}

/* Resize handle styling */
.cursor-col-resize {
  cursor: col-resize !important;
}

/* Prevent text selection during resize */
.select-none {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

/* Smooth panel transitions */
aside[style*="width"] {
  transition: width 0.1s ease-out;
}
</style>