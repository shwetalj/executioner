<template>
  <div class="h-full relative overflow-hidden" :class="theme ? theme.canvasBg : 'bg-gray-50'">
    <!-- Grid background -->
    <div class="absolute inset-0 pointer-events-none" 
         :style="showGrid ? getGridStyle() : { display: 'none' }"></div>
    
    <!-- Canvas -->
    <div class="drop-zone relative h-full overflow-hidden"
         tabindex="0"
         @drop.prevent="handleDrop"
         @dragover.prevent="handleDragOver"
         @dragleave="handleDragLeave"
         @contextmenu.prevent="showContextMenu"
         @mousedown="handleCanvasMouseDown"
         @mousemove="handleCanvasMouseMove"
         @mouseup="handleCanvasMouseUp"
         @mouseleave="handleCanvasMouseLeave"
         @wheel="handleCanvasWheel"
         @click="focusCanvas"
         :style="{ cursor: canvasCursor }">
      
      <!-- Canvas content wrapper with transform -->
      <div class="canvas-content" 
           :style="{ 
             transform: `translate(${canvasTransform.x}px, ${canvasTransform.y}px) scale(${zoom})`,
             transformOrigin: '0 0',
             transition: isPanning ? 'none' : 'transform 0.1s'
           }">
      
      <!-- SVG for connections -->
      <svg class="absolute pointer-events-none" style="width: 5000px; height: 5000px; left: 0; top: 0;">
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="8" 
                  refX="7" refY="4" orient="auto">
            <path d="M0,0 L0,8 L8,4 z" :fill="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'" />
          </marker>
        </defs>
        
        <!-- Connection lines -->
        <g v-for="connection in connections" :key="`${connection.from}-${connection.to}`">
          <!-- Main connection line -->
          <path :d="getConnectionPath(connection)" 
                class="connection-line pointer-events-auto"
                :stroke="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'"
                stroke-width="2"
                fill="none"
                :opacity="0.7"
                marker-end="url(#arrowhead)"
                @click="selectConnection(connection)"
                @contextmenu.prevent.stop="showConnectionContextMenu($event, connection)"
                style="cursor: pointer; transition: all 0.2s" />
          <!-- Connection label (hidden by default) -->
          <!-- <text :x="getConnectionMidpoint(connection).x" 
                :y="getConnectionMidpoint(connection).y - 10"
                text-anchor="middle" 
                class="text-xs fill-gray-500 pointer-events-none">
            {{ connection.from }} → {{ connection.to }}
          </text> -->
        </g>
      </svg>
      
      <!-- Job nodes -->
      <div v-for="job in jobs" :key="job.id"
           :ref="`node-${job.id}`"
           :style="{ left: `${job.x}px`, top: `${job.y}px` }"
           class="job-node absolute rounded-md shadow border select-none transition-all"
           :class="[
             theme ? theme.nodeBg : 'bg-white',
             theme ? theme.border : 'border-gray-300',
             nodeViewMode === 'compact' ? 'p-2 w-48' : 'p-3 w-64',
             isNodeSelected(job.id) ? (theme ? theme.nodeSelected : 'border-indigo-500 shadow-lg ring-2 ring-indigo-200') : (theme ? theme.nodeHover : 'hover:border-indigo-300'),
             { 'cursor-grabbing': isDragging && (draggedNode?.id === job.id || draggedNodes.some(n => n.id === job.id)), 
               'cursor-grab': !isDragging }
           ]"
           @mousedown="startNodeDrag($event, job)"
           @click="handleNodeClick($event, job)"
           @contextmenu.prevent.stop="showNodeContextMenu($event, job)">
        
        <!-- Connection points -->
        <div class="absolute -top-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 rounded-full cursor-pointer opacity-0 hover:opacity-100 transition-opacity"
             :class="[{ 'opacity-100': isConnecting || selectedNode === job.id }, theme ? theme.accent : 'bg-indigo-500']"
             @mousedown.stop="startConnection($event, job.id, 'in')"></div>
        <div class="absolute -bottom-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 rounded-full cursor-pointer opacity-0 hover:opacity-100 transition-opacity"
             :class="[{ 'opacity-100': isConnecting || selectedNode === job.id }, theme ? theme.accent : 'bg-indigo-500']"
             @mousedown.stop="startConnection($event, job.id, 'out')"></div>
        
        <!-- Job content -->
        <div class="flex items-center justify-between gap-1">
          <div class="flex items-center gap-1 flex-1 min-w-0">
            <i v-if="isNodeSelected(job.id)" class="fas fa-check-circle text-green-500 text-xs flex-shrink-0"></i>
            <input v-if="editingNodeId === job.id"
                   v-model="editingNodeName"
                   @blur="finishRename"
                   @keyup.enter="finishRename"
                   @keyup.escape="cancelRename"
                   @click.stop
                   class="flex-1 px-1 py-0 text-sm font-medium border rounded outline-none bg-white text-gray-900 border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                   :ref="`renameInput-${job.id}`"
                   autofocus />
            <h3 v-else class="font-medium truncate text-sm flex-1" :class="theme ? theme.text : 'text-gray-900'">{{ job.id }}</h3>
          </div>
          <div v-if="job.dependencies && job.dependencies.length > 0" class="flex-shrink-0">
            <span class="text-xs" :class="theme ? theme.textMuted : 'text-gray-400'" :title="`${job.dependencies.length} dependencies`">
              <i class="fas fa-link text-xs"></i>
            </span>
          </div>
        </div>
        
        <!-- Description only in normal mode -->
        <p v-if="nodeViewMode === 'normal' && job.description" class="text-xs truncate mt-1" :class="theme ? theme.textMuted : 'text-gray-500'" :title="job.description">
          {{ job.description }}
        </p>
      </div>
      
      <!-- Temporary connection line while dragging -->
      <svg v-if="isConnecting" class="absolute pointer-events-none" style="width: 5000px; height: 5000px; left: 0; top: 0;">
        <line :x1="tempConnection.x1" :y1="tempConnection.y1"
              :x2="tempConnection.x2" :y2="tempConnection.y2"
              :stroke="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'"
              stroke-width="2" stroke-dasharray="5,5" />
      </svg>
      
      <!-- Lasso Selection Overlay -->
      <div v-if="isLassoSelecting" 
           class="absolute border-2 border-blue-500 bg-blue-500 bg-opacity-10 pointer-events-none"
           :style="{
             left: Math.min(lassoSelection.startX, lassoSelection.endX) + 'px',
             top: Math.min(lassoSelection.startY, lassoSelection.endY) + 'px',
             width: Math.abs(lassoSelection.endX - lassoSelection.startX) + 'px',
             height: Math.abs(lassoSelection.endY - lassoSelection.startY) + 'px'
           }">
      </div>
      </div> <!-- End of canvas-content -->
    </div> <!-- End of drop-zone -->
    
    <!-- Selection Info -->
    <div v-if="totalSelectedCount > 0" class="absolute top-4 left-4 px-3 py-2 rounded-lg shadow-lg" 
         :class="[theme ? theme.nodeBg : 'bg-white', theme ? theme.border : 'border-gray-200']">
      <span class="text-sm font-medium" :class="theme ? theme.text : 'text-gray-900'">
        <i class="fas fa-check-square mr-1"></i>{{ totalSelectedCount }} node{{ totalSelectedCount > 1 ? 's' : '' }} selected
      </span>
      <span v-if="selectedNode && selectedNodes.length === 0" class="text-xs ml-2 opacity-75">(single)</span>
      <span v-if="selectedNodes.length > 0" class="text-xs ml-2 opacity-75">(multi)</span>
    </div>
    
    <!-- Pan Mode Indicator -->
    <div v-if="(panToolActive || spacePressed) && !isPanning" class="absolute top-4 left-1/2 transform -translate-x-1/2 px-3 py-2 rounded-lg shadow-lg pointer-events-none" 
         :class="[theme ? theme.nodeBg : 'bg-white', theme ? theme.border : 'border-gray-200']">
      <span class="text-sm font-medium" :class="theme ? theme.text : 'text-gray-900'">
        <i class="fas fa-hand-paper mr-1"></i>Pan Mode - Drag to pan canvas
      </span>
    </div>
    
    <!-- Keyboard Shortcuts Help -->
    <div class="absolute top-4 right-4 text-xs opacity-50 hover:opacity-100 transition-opacity">
      <details class="cursor-pointer">
        <summary class="px-2 py-1 rounded" :class="[theme ? theme.surface : 'bg-white', theme ? theme.text : 'text-gray-700']">
          <i class="fas fa-keyboard mr-1"></i>Shortcuts
        </summary>
        <div class="mt-1 p-2 rounded-lg shadow-lg" :class="[theme ? theme.surface : 'bg-white', theme ? theme.border : 'border-gray-200']">
          <div class="space-y-1">
            <div><kbd>Space</kbd> + Drag to pan</div>
            <div><kbd>Shift</kbd> + Drag to pan</div>
            <div><kbd>Delete</kbd> Remove selected</div>
            <div><kbd>Ctrl+A</kbd> Select all</div>
            <div><kbd>Ctrl+C/X/V</kbd> Copy/Cut/Paste</div>
            <div><kbd>Ctrl+D</kbd> Duplicate</div>
            <div><kbd>F2</kbd> Rename node</div>
            <div><kbd>←↑→↓</kbd> Nudge (Shift=fast)</div>
            <div><kbd>Esc</kbd> Clear selection</div>
          </div>
        </div>
      </details>
    </div>
    
    <!-- Canvas controls -->
    <div class="absolute bottom-4 right-4 flex flex-col space-y-2">
      <!-- Control buttons row -->
      <div class="flex space-x-2">
        <!-- Tool Selection & Grid Toggle -->
        <div class="rounded-lg shadow p-1 flex space-x-1" :class="theme ? theme.surface : 'bg-white'">
          <button @click="togglePanTool" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          panToolActive 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  :title="panToolActive ? 'Pan Tool Active (click to deactivate)' : 'Activate Pan Tool (or hold Space)'">
            <i class="fas fa-hand-paper"></i>
          </button>
          <div class="w-px bg-gray-300 mx-1"></div>
          <button @click="toggleGrid" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          showGrid 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  :title="showGrid ? 'Hide Grid' : 'Show Grid'">
            <i class="fas fa-border-all"></i>
          </button>
          <button @click="toggleSnapToGrid" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          snapToGrid 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  :title="snapToGrid ? 'Disable Snap to Grid' : 'Enable Snap to Grid'">
            <i class="fas fa-magnet"></i>
          </button>
          <button @click="toggleAutoReflow" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          autoReflowEnabled 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  :title="autoReflowEnabled ? 'Disable Auto-reflow on resize' : 'Enable Auto-reflow on resize'">
            <i class="fas fa-compress-arrows-alt"></i>
          </button>
        </div>
        
        <!-- View Mode Toggle -->
        <div class="rounded-lg shadow p-1 flex space-x-1" :class="theme ? theme.surface : 'bg-white'">
          <button @click="nodeViewMode = 'compact'" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          nodeViewMode === 'compact' 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  title="Compact View">
            <i class="fas fa-compress"></i>
          </button>
          <button @click="nodeViewMode = 'normal'" 
                  :class="['px-3 py-1 text-sm rounded transition-colors', 
                          nodeViewMode === 'normal' 
                            ? (theme ? [theme.accent, theme.accentText] : 'bg-indigo-600 text-white')
                            : (theme ? [theme.text, theme.surfaceHover] : 'text-gray-600 hover:bg-gray-100')]"
                  title="Normal View">
            <i class="fas fa-expand-arrows-alt"></i>
          </button>
        </div>
        
        <!-- Auto-arrange Button with dropdown -->
        <div class="relative">
          <button @click="showArrangeMenu = !showArrangeMenu" 
                  class="p-2 rounded-lg shadow transition-colors" 
                  :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                  title="Auto-arrange layouts">
            <i class="fas fa-magic"></i>
          </button>
        <div v-if="showArrangeMenu" 
             class="absolute right-0 bottom-full mb-2 w-56 rounded-lg shadow-lg z-50 border py-1"
             :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'">
          <button @click="autoArrangeDefault(); showArrangeMenu = false" 
                  class="w-full px-4 py-2 text-left flex items-center transition-colors" 
                  :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
            <i class="fas fa-magic mr-3"></i>Smart Auto
          </button>
          <button @click="autoArrangeHierarchy(); showArrangeMenu = false" 
                  class="w-full px-4 py-2 text-left flex items-center transition-colors" 
                  :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
            <i class="fas fa-sitemap mr-3"></i>Layered
          </button>
          <button @click="autoArrangeTreeHorizontal(); showArrangeMenu = false" 
                  class="w-full px-4 py-2 text-left flex items-center transition-colors" 
                  :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
            <i class="fas fa-arrows-alt-h mr-3"></i>Tree (Horizontal)
          </button>
          <button @click="autoArrangeTree(); showArrangeMenu = false" 
                  class="w-full px-4 py-2 text-left flex items-center transition-colors" 
                  :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
            <i class="fas fa-tree mr-3"></i>Tree (Vertical)
          </button>
        </div>
        </div>
      </div>
      
      <!-- Zoom Controls -->
      <div class="flex items-center space-x-2">
        <div class="px-2 py-1 rounded shadow text-xs font-mono" 
             :class="theme ? [theme.surface, theme.text] : 'bg-white'">
          {{ Math.round(zoom * 100) }}%
        </div>
        <button @click="zoomOut" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Zoom Out">
          <i class="fas fa-search-minus"></i>
        </button>
        <button @click="zoomIn" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Zoom In">
          <i class="fas fa-search-plus"></i>
        </button>
        <button @click="fitToScreen" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Fit to Screen">
          <i class="fas fa-expand"></i>
        </button>
        <button @click="resetView" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Reset View (100% zoom, centered)">
          <i class="fas fa-compress-arrows-alt"></i>
        </button>
      </div>
    </div>
    
    <!-- Context Menu -->
    <div v-if="showMenu" 
         :style="{ left: `${menuPosition.x}px`, top: `${menuPosition.y}px` }"
         class="absolute z-50 rounded-lg shadow-lg border py-1 min-w-48"
         :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'"
         @click.stop>
      
      <!-- Node Context Menu -->
      <template v-if="menuType === 'node'">
        <button @click="renameNode" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-pencil-alt mr-3"></i>Rename <span class="text-xs ml-auto opacity-50">F2</span>
        </button>
        <button @click="editNodeProperties" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-cog mr-3"></i>Edit Properties
        </button>
        <div class="border-t my-1" :class="theme ? theme.border : 'border-gray-200'"></div>
        <button @click="duplicateNode" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-copy mr-3"></i>Duplicate <span class="text-xs ml-auto opacity-50">Ctrl+D</span>
        </button>
        <button @click="copyNode" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-clipboard mr-3"></i>Copy <span class="text-xs ml-auto opacity-50">Ctrl+C</span>
        </button>
        <button @click="cutNode" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-cut mr-3"></i>Cut <span class="text-xs ml-auto opacity-50">Ctrl+X</span>
        </button>
        <div class="border-t my-1" :class="theme ? theme.border : 'border-gray-200'"></div>
        <button @click="deleteNode" class="w-full px-4 py-2 text-left flex items-center text-red-600 transition-colors" :class="theme ? theme.surfaceHover : 'hover:bg-gray-100'">
          <i class="fas fa-trash mr-3"></i>Delete <span class="text-xs ml-auto opacity-50">Del</span>
        </button>
      </template>
      
      <!-- Connection Context Menu -->
      <template v-else-if="menuType === 'connection'">
        <button @click="editConnectionProperties" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-cog mr-3"></i>Edit Connection
        </button>
        <button @click="deleteConnection" class="w-full px-4 py-2 text-left flex items-center text-red-600 transition-colors" :class="theme ? theme.surfaceHover : 'hover:bg-gray-100'">
          <i class="fas fa-unlink mr-3"></i>Delete Connection
        </button>
      </template>
      
      <!-- Canvas Context Menu -->
      <template v-else>
        <button v-if="hasClipboard" @click="pasteNodes" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-paste mr-3"></i>Paste <span class="text-xs ml-auto opacity-50">Ctrl+V</span>
        </button>
        <button @click="selectAllNodes" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-check-square mr-3"></i>Select All <span class="text-xs ml-auto opacity-50">Ctrl+A</span>
        </button>
        <div class="border-t my-1" :class="theme ? theme.border : 'border-gray-200'"></div>
        <button @click="autoArrangeDefault" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-magic mr-3"></i>Auto-arrange
        </button>
        <button @click="autoArrangeHierarchy" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-sitemap mr-3"></i>Layered Layout
        </button>
        <button @click="autoArrangeTree" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-tree mr-3"></i>Tree (Vertical)
        </button>
        <button @click="autoArrangeTreeHorizontal" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
          <i class="fas fa-arrows-alt-h mr-3"></i>Tree (Horizontal)
        </button>
        <div class="border-t my-1" :class="theme ? theme.border : 'border-gray-200'"></div>
        <button @click="clearCanvas" class="w-full px-4 py-2 text-left flex items-center text-red-600 transition-colors" :class="theme ? theme.surfaceHover : 'hover:bg-gray-100'">
          <i class="fas fa-trash mr-3"></i>Clear Canvas
        </button>
      </template>
    </div>
  </div>
</template>

<script>
export default {
  name: 'WorkflowCanvas',
  props: {
    jobs: {
      type: Array,
      default: () => []
    },
    connections: {
      type: Array,
      default: () => []
    },
    theme: {
      type: Object,
      default: null
    },
    autoReflow: {
      type: Boolean,
      default: true
    }
  },
  data() {
    return {
      selectedNode: null,
      selectedNodes: [], // Multi-selection support
      isDragging: false,
      draggedNode: null,
      draggedNodes: [], // For dragging multiple nodes
      dragOffset: { x: 0, y: 0 },
      dragInitialPositions: {}, // Store initial positions during drag
      isConnecting: false,
      connectingFrom: null,
      tempConnection: { x1: 0, y1: 0, x2: 0, y2: 0 },
      zoom: 1,
      isDragOver: false,
      showMenu: false,
      menuPosition: { x: 0, y: 0 },
      menuType: null, // 'node', 'canvas', 'connection'
      menuTarget: null, // The target node or connection
      nodeViewMode: 'normal', // 'compact' or 'normal'
      showArrangeMenu: false, // Show auto-arrange dropdown
      // Inline editing
      editingNodeId: null,
      editingNodeName: '',
      renameCancelled: false,
      // Grid settings
      gridEnabled: true,
      snapToGrid: true,
      gridSize: 20, // Grid size in pixels
      showGrid: true, // Visual grid display
      // Canvas dimensions
      canvasWidth: 0,
      canvasHeight: 0,
      resizeObserver: null,
      autoReflowEnabled: true,
      // Canvas panning
      isPanning: false,
      spacePressed: false,
      panToolActive: false,
      panStart: { x: 0, y: 0 },
      canvasOffset: { x: 0, y: 0 },
      canvasTransform: { x: 0, y: 0 },
      // Lasso selection
      isLassoSelecting: false,
      lassoSelection: {
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0,
        ctrlKey: false
      }
    };
  },
  watch: {
    jobs: {
      immediate: true,
      deep: true,
      handler(newJobs, oldJobs) {
        // Auto-arrange if we receive jobs that need positioning
        if (newJobs && newJobs.length > 0) {
          // Check if ALL jobs are at the same position (stacked)
          const firstJob = newJobs[0];
          const allStacked = newJobs.every(job => 
            job.x === firstJob.x && job.y === firstJob.y
          );
          
          if (allStacked) {
            // Use setTimeout to ensure DOM is ready
            setTimeout(() => {
              console.log('Jobs are stacked, auto-arranging with layered layout...');
              this.autoArrangeHierarchy();
            }, 100);
          }
        }
      }
    }
  },
  mounted() {
    document.addEventListener('click', this.hideMenus);
    document.addEventListener('keydown', this.handleKeyDown);
    document.addEventListener('keyup', this.handleKeyUp);
    
    // Focus canvas on mount for keyboard shortcuts
    this.$nextTick(() => {
      this.focusCanvas();
    });
    
    // Load grid preferences
    const savedShowGrid = localStorage.getItem('canvas-showGrid');
    if (savedShowGrid !== null) {
      this.showGrid = savedShowGrid === 'true';
    }
    const savedSnapToGrid = localStorage.getItem('canvas-snapToGrid');
    if (savedSnapToGrid !== null) {
      this.snapToGrid = savedSnapToGrid === 'true';
    }
    const savedAutoReflow = localStorage.getItem('canvas-autoReflow');
    if (savedAutoReflow !== null) {
      this.autoReflowEnabled = savedAutoReflow === 'true';
    }
    
    // Set up resize observer
    this.setupResizeObserver();
  },
  beforeUnmount() {
    document.removeEventListener('click', this.hideMenus);
    document.removeEventListener('keydown', this.handleKeyDown);
    document.removeEventListener('keyup', this.handleKeyUp);
    
    // Clean up resize observer
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
  },
  methods: {
    focusCanvas() {
      // Ensure canvas has focus for keyboard shortcuts
      const canvas = this.$el.querySelector('.drop-zone');
      if (canvas) {
        canvas.focus();
        console.log('Canvas focused for keyboard shortcuts');
      }
    },
    handleDrop(event) {
      this.isDragOver = false;
      // Pass grid settings with the event
      this.$emit('drop', event, { 
        snapToGrid: this.snapToGrid, 
        gridSize: this.gridSize 
      });
    },
    handleDragOver(event) {
      this.isDragOver = true;
      event.dataTransfer.dropEffect = 'copy';
    },
    handleDragLeave() {
      this.isDragOver = false;
    },
    selectNode(nodeId) {
      // Clear multi-selection and select single node
      this.selectedNodes = [];
      this.selectedNode = nodeId;
      this.$emit('select-job', nodeId);
    },
    // Multi-selection methods
    isNodeSelected(nodeId) {
      return this.selectedNodes.includes(nodeId) || this.selectedNode === nodeId;
    },
    handleNodeClick(event, job) {
      event.stopPropagation();
      
      // Don't change selection when editing
      if (this.editingNodeId === job.id) return;
      
      if (event.shiftKey && this.selectedNodes.length > 0) {
        // Shift+Click: Select range (not implemented for canvas, but could be)
        this.selectNodeRange(job);
      } else if (event.ctrlKey || event.metaKey) {
        // Ctrl/Cmd+Click: Toggle individual selection
        const index = this.selectedNodes.indexOf(job.id);
        if (index > -1) {
          // Remove from selection
          this.selectedNodes.splice(index, 1);
          // If this was the selectedNode, clear it
          if (this.selectedNode === job.id) {
            this.selectedNode = null;
          }
        } else {
          // Add to selection
          this.selectedNodes.push(job.id);
          // Clear single selection when building multi-selection
          this.selectedNode = null;
        }
      } else {
        // Regular click: Select single node
        this.selectedNodes = [];
        this.selectedNode = job.id;
        this.$emit('select-job', job.id);
      }
    },
    selectNodeRange(toNode) {
      // For canvas, range selection could be based on position or creation order
      // For now, just add to selection
      if (!this.selectedNodes.includes(toNode.id)) {
        this.selectedNodes.push(toNode.id);
      }
    },
    clearSelection() {
      this.selectedNodes = [];
      this.selectedNode = null;
    },
    // Keyboard shortcuts
    handleKeyDown(event) {
      // Log all Ctrl/Cmd key combinations for debugging
      if (event.ctrlKey || event.metaKey) {
        console.log(`Key pressed: ${event.ctrlKey ? 'Ctrl' : 'Cmd'}+${event.key}`);
      }
      
      // Space key for panning
      if (event.code === 'Space' && !this.spacePressed) {
        this.spacePressed = true;
        event.preventDefault();
        return;
      }
      
      // Only handle shortcuts when canvas or its children have focus
      // Also allow if the WorkflowCanvas component itself has focus
      const canvasElement = this.$el;
      const activeElement = document.activeElement;
      
      if (!canvasElement) {
        console.log('Canvas element not found');
        return;
      }
      
      // Check if focus is within canvas, or body, or the canvas itself
      const focusInCanvas = canvasElement.contains(activeElement);
      const focusOnBody = activeElement === document.body;
      const focusOnCanvas = activeElement === canvasElement;
      
      if (!focusInCanvas && !focusOnBody && !focusOnCanvas) {
        console.log('Focus not in canvas - shortcuts disabled', {
          focusInCanvas,
          focusOnBody,
          focusOnCanvas,
          activeElement: activeElement.tagName
        });
        return;
      }
      
      // Don't handle shortcuts when typing in input fields
      if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
        return;
      }
      
      // F2 - Rename selected node (inline)
      if (event.key === 'F2') {
        event.preventDefault();
        if (this.selectedNode || (this.selectedNodes.length === 1)) {
          const nodeId = this.selectedNode || this.selectedNodes[0];
          this.startInlineRename(nodeId);
        }
      }
      
      // Delete key - Remove selected nodes
      else if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        this.deleteSelectedNodes();
      }
      
      // Ctrl/Cmd + A - Select all nodes
      else if ((event.ctrlKey || event.metaKey) && event.key === 'a') {
        event.preventDefault();
        this.selectAllNodes();
      }
      
      // Ctrl/Cmd + C - Copy selected nodes
      else if ((event.ctrlKey || event.metaKey) && event.key === 'c') {
        event.preventDefault();
        this.copySelectedNodes();
      }
      
      // Ctrl/Cmd + X - Cut selected nodes
      else if ((event.ctrlKey || event.metaKey) && event.key === 'x') {
        event.preventDefault();
        this.cutSelectedNodes();
      }
      
      // Ctrl/Cmd + V - Paste nodes
      else if ((event.ctrlKey || event.metaKey) && event.key === 'v') {
        event.preventDefault();
        this.pasteNodes();
      }
      
      // Ctrl/Cmd + D - Duplicate selected nodes
      else if ((event.ctrlKey || event.metaKey) && event.key === 'd') {
        event.preventDefault();
        this.duplicateSelectedNodes();
      }
      
      // Escape - Clear selection
      else if (event.key === 'Escape') {
        event.preventDefault();
        this.clearSelection();
      }
      
      // Arrow keys - Nudge selected nodes
      else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
        event.preventDefault();
        const distance = event.shiftKey ? 50 : 10; // Shift for larger moves
        this.nudgeSelectedNodes(event.key, distance);
      }
    },
    handleKeyUp(event) {
      // Release space key
      if (event.code === 'Space') {
        this.spacePressed = false;
        if (this.isPanning) {
          this.stopPanning();
        }
      }
    },
    deleteSelectedNodes() {
      if (this.selectedNodes.length > 0 || this.selectedNode) {
        // Combine both selection types
        let nodesToDelete = [...this.selectedNodes];
        if (this.selectedNode && !nodesToDelete.includes(this.selectedNode)) {
          nodesToDelete.push(this.selectedNode);
        }
        
        // Remove any nulls or undefineds
        nodesToDelete = nodesToDelete.filter(id => id);
        
        console.log('Deleting nodes:', nodesToDelete);
        
        // Emit event to parent to handle deletion
        this.$emit('delete-nodes', nodesToDelete);
        this.clearSelection();
      }
    },
    selectAllNodes() {
      this.selectedNodes = this.jobs.map(job => job.id);
      this.selectedNode = null;
    },
    copySelectedNodes() {
      console.log('copySelectedNodes called', {
        selectedNodes: this.selectedNodes,
        selectedNode: this.selectedNode
      });
      
      if (this.selectedNodes.length > 0 || this.selectedNode) {
        // Combine both selection types
        let nodesToCopy = [...this.selectedNodes];
        if (this.selectedNode && !nodesToCopy.includes(this.selectedNode)) {
          nodesToCopy.push(this.selectedNode);
        }
        
        // Remove any nulls or undefineds
        nodesToCopy = nodesToCopy.filter(id => id);
        
        console.log('Nodes to copy:', nodesToCopy);
        
        // Get the selected nodes
        const copiedJobs = this.jobs.filter(job => nodesToCopy.includes(job.id));
        
        console.log('Found jobs:', copiedJobs);
        
        // Get ONLY connections between selected nodes (internal subgraph connections)
        // Both from AND to must be in the selected nodes
        const copiedConnections = this.connections.filter(conn => 
          nodesToCopy.includes(conn.from) && nodesToCopy.includes(conn.to)
        );
        
        console.log('Found connections (internal only):', copiedConnections);
        console.log('Excluded external connections:', 
          this.connections.filter(conn => 
            (nodesToCopy.includes(conn.from) || nodesToCopy.includes(conn.to)) &&
            !(nodesToCopy.includes(conn.from) && nodesToCopy.includes(conn.to))
          )
        );
        
        // Deep clone the data to avoid reference issues
        const clipboardData = {
          type: 'subgraph',
          nodes: JSON.parse(JSON.stringify(copiedJobs)),  // Deep clone
          connections: JSON.parse(JSON.stringify(copiedConnections)),  // Deep clone
          timestamp: Date.now()
        };
        
        localStorage.setItem('canvas-clipboard', JSON.stringify(clipboardData));
        
        // Visual feedback
        console.log(`Copied ${copiedJobs.length} nodes and ${copiedConnections.length} connections to clipboard`);
        console.log('Clipboard data:', clipboardData);
      } else {
        console.log('No nodes selected to copy');
      }
    },
    cutSelectedNodes() {
      console.log('cutSelectedNodes called');
      console.log('Before copy - selectedNodes:', this.selectedNodes);
      console.log('Before copy - selectedNode:', this.selectedNode);
      
      this.copySelectedNodes();
      
      console.log('After copy, before delete - selectedNodes:', this.selectedNodes);
      console.log('After copy, before delete - selectedNode:', this.selectedNode);
      
      this.deleteSelectedNodes();
      
      console.log('After delete - selectedNodes:', this.selectedNodes);
      console.log('After delete - selectedNode:', this.selectedNode);
    },
    pasteNodes(event) {
      console.log('pasteNodes called', event);
      const clipboardData = localStorage.getItem('canvas-clipboard');
      console.log('Raw clipboard data:', clipboardData);
      
      if (clipboardData) {
        try {
          const parsed = JSON.parse(clipboardData);
          console.log('Parsed clipboard:', parsed);
          
          // Handle both old format (type: 'nodes') and new format (type: 'subgraph')
          if ((parsed.type === 'nodes' || parsed.type === 'subgraph') && (parsed.data || parsed.nodes)) {
            // Get paste position - use menu position, mouse position, or default
            let pastePosition;
            
            // If called from context menu, use menu position
            if (this.menuPosition) {
              pastePosition = { ...this.menuPosition };
            } 
            // If called from keyboard shortcut, calculate position from mouse or use center
            else {
              const canvas = this.$el.querySelector('.drop-zone');
              const rect = canvas.getBoundingClientRect();
              
              // Calculate center of visible area in canvas coordinates
              // We need to account for zoom and transform
              const centerX = (rect.width / 2 - this.canvasTransform.x) / this.zoom;
              const centerY = (rect.height / 2 - this.canvasTransform.y) / this.zoom;
              
              pastePosition = {
                x: centerX,
                y: centerY
              };
              
              console.log('Calculated paste position for keyboard shortcut:', pastePosition);
              console.log('Canvas transform:', this.canvasTransform, 'Zoom:', this.zoom);
            }
            
            console.log('Initial paste position:', pastePosition);
            
            if (this.snapToGrid) {
              pastePosition.x = Math.round(pastePosition.x / this.gridSize) * this.gridSize;
              pastePosition.y = Math.round(pastePosition.y / this.gridSize) * this.gridSize;
              console.log('Snapped paste position:', pastePosition);
            }
            
            // Prepare paste data with nodes and connections
            const pasteData = {
              nodes: parsed.nodes || parsed.data || [],
              connections: parsed.connections || [],
              position: pastePosition,
              isSubgraph: parsed.type === 'subgraph'
            };
            
            console.log('Emitting paste-nodes with data:', pasteData);
            this.$emit('paste-nodes', pasteData);
            
            // Visual feedback
            console.log(`Pasting ${pasteData.nodes.length} nodes and ${pasteData.connections.length} connections`);
          } else {
            console.log('Invalid clipboard format:', parsed);
          }
        } catch (e) {
          console.error('Failed to paste:', e);
        }
      } else {
        console.log('No clipboard data found');
      }
      this.hideContextMenu();
    },
    duplicateSelectedNodes() {
      if (this.selectedNodes.length > 0 || this.selectedNode) {
        // Combine both selection types
        let nodesToDuplicate = [...this.selectedNodes];
        if (this.selectedNode && !nodesToDuplicate.includes(this.selectedNode)) {
          nodesToDuplicate.push(this.selectedNode);
        }
        
        // Remove any nulls or undefineds
        nodesToDuplicate = nodesToDuplicate.filter(id => id);
        
        // Find the jobs to duplicate from the props
        const jobsToDuplicate = this.jobs.filter(job => nodesToDuplicate.includes(job.id));
        this.$emit('duplicate-nodes', jobsToDuplicate);
      }
    },
    nudgeSelectedNodes(direction, distance) {
      if (this.selectedNodes.length === 0 && !this.selectedNode) return;
      
      const nodesToNudge = this.selectedNodes.length > 0 ? 
        this.selectedNodes : [this.selectedNode];
      
      // Use grid size for nudging if snap to grid is enabled
      const nudgeDistance = this.snapToGrid ? this.gridSize : distance;
      const deltaX = direction === 'ArrowLeft' ? -nudgeDistance : 
                     direction === 'ArrowRight' ? nudgeDistance : 0;
      const deltaY = direction === 'ArrowUp' ? -nudgeDistance : 
                     direction === 'ArrowDown' ? nudgeDistance : 0;
      
      // Create position updates for selected nodes only
      const updates = [];
      this.jobs.forEach(job => {
        if (nodesToNudge.includes(job.id)) {
          let newX = Math.max(0, (job.x || 0) + deltaX);
          let newY = Math.max(0, (job.y || 0) + deltaY);
          
          // Ensure we stay on grid
          if (this.snapToGrid) {
            newX = Math.round(newX / this.gridSize) * this.gridSize;
            newY = Math.round(newY / this.gridSize) * this.gridSize;
          }
          
          updates.push({
            id: job.id,
            x: newX,
            y: newY
          });
        }
      });
      
      // Emit position updates
      this.$emit('update-positions', updates);
    },
    // Canvas interaction methods
    handleCanvasMouseDown(event) {
      // Check what was clicked
      const isNode = event.target.closest('.job-node');
      const isConnection = event.target.closest('path');
      const isControl = event.target.closest('.canvas-controls');
      
      // Don't start canvas operations if clicking on controls
      if (isControl) return;
      
      // Handle panning first (takes priority)
      if (this.panToolActive || this.spacePressed || event.shiftKey) {
        // Pan tool active, Space or Shift + drag = pan (works anywhere on canvas)
        event.preventDefault();
        this.startPanning(event);
        return;
      } else if (event.button === 1) {
        // Middle mouse button = pan
        event.preventDefault();
        this.startPanning(event);
        return;
      }
      
      // Only do other operations if not on a node or connection
      const isEmptySpace = !isNode && !isConnection;
      if (isEmptySpace && event.button === 0) {
        // Left click on empty space = lasso selection
        this.startLassoSelection(event);
      }
    },
    handleCanvasMouseMove(event) {
      if (this.isPanning) {
        this.updatePanning(event);
      } else if (this.isLassoSelecting) {
        this.updateLassoSelection(event);
      }
    },
    handleCanvasMouseUp(event) {
      if (this.isPanning) {
        this.stopPanning();
      } else if (this.isLassoSelecting) {
        this.endLassoSelection();
      }
    },
    handleCanvasMouseLeave(event) {
      if (this.isPanning) {
        this.stopPanning();
      }
      if (this.isLassoSelecting) {
        this.endLassoSelection();
      }
    },
    handleCanvasWheel(event) {
      if (event.ctrlKey || event.metaKey) {
        // Ctrl/Cmd + scroll = zoom
        event.preventDefault();
        const delta = event.deltaY > 0 ? 0.9 : 1.1;
        this.zoomCanvas(delta, event);
      } else {
        // Regular scroll = pan
        event.preventDefault();
        this.canvasTransform.x -= event.deltaX;
        this.canvasTransform.y -= event.deltaY;
      }
    },
    // Panning methods
    startPanning(event) {
      this.isPanning = true;
      this.panStart = {
        x: event.clientX - this.canvasTransform.x,
        y: event.clientY - this.canvasTransform.y
      };
      // Clear any selection when starting to pan
      this.clearSelection();
      event.preventDefault();
      event.stopPropagation();
    },
    updatePanning(event) {
      if (!this.isPanning) return;
      
      this.canvasTransform.x = event.clientX - this.panStart.x;
      this.canvasTransform.y = event.clientY - this.panStart.y;
      event.preventDefault();
    },
    stopPanning() {
      this.isPanning = false;
    },
    // Zoom methods
    zoomCanvas(delta, event) {
      const oldZoom = this.zoom;
      const newZoom = Math.min(Math.max(0.1, this.zoom * delta), 3); // Limit zoom between 0.1x and 3x
      
      if (event) {
        // Zoom towards mouse position
        const canvas = this.$el.querySelector('.drop-zone');
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        // Adjust transform to zoom towards mouse position
        const scaleDiff = newZoom - oldZoom;
        this.canvasTransform.x -= (x - this.canvasTransform.x) * (scaleDiff / oldZoom);
        this.canvasTransform.y -= (y - this.canvasTransform.y) * (scaleDiff / oldZoom);
      }
      
      this.zoom = newZoom;
    },
    // Lasso selection methods
    startLassoSelection(event) {
      // Only start lasso if clicking on empty canvas (not on a node)
      if (event.target.closest('.job-node')) return;
      
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      
      this.isLassoSelecting = true;
      // Account for canvas transform when calculating positions
      this.lassoSelection.startX = (event.clientX - rect.left - this.canvasTransform.x) / this.zoom;
      this.lassoSelection.startY = (event.clientY - rect.top - this.canvasTransform.y) / this.zoom;
      this.lassoSelection.endX = this.lassoSelection.startX;
      this.lassoSelection.endY = this.lassoSelection.startY;
      this.lassoSelection.ctrlKey = event.ctrlKey || event.metaKey;
      
      // Clear previous selection unless Ctrl/Cmd is held
      if (!event.ctrlKey && !event.metaKey) {
        this.selectedNodes = [];
        this.selectedNode = null;
      }
    },
    updateLassoSelection(event) {
      if (!this.isLassoSelecting) return;
      
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      
      // Account for canvas transform when calculating positions
      this.lassoSelection.endX = (event.clientX - rect.left - this.canvasTransform.x) / this.zoom;
      this.lassoSelection.endY = (event.clientY - rect.top - this.canvasTransform.y) / this.zoom;
      
      // Update selected nodes in the lasso area
      this.updateSelectedNodesInArea();
    },
    endLassoSelection() {
      this.isLassoSelecting = false;
    },
    updateSelectedNodesInArea() {
      const selectionRect = {
        left: Math.min(this.lassoSelection.startX, this.lassoSelection.endX),
        top: Math.min(this.lassoSelection.startY, this.lassoSelection.endY),
        right: Math.max(this.lassoSelection.startX, this.lassoSelection.endX),
        bottom: Math.max(this.lassoSelection.startY, this.lassoSelection.endY)
      };
      
      const initialSelection = [...this.selectedNodes];
      const lassoSelection = [];
      
      this.jobs.forEach(job => {
        // Check if job center is within selection
        const jobCenterX = job.x + 68; // Half of node width (136px / 2)
        const jobCenterY = job.y + 20; // Approximate half height
        
        if (jobCenterX >= selectionRect.left &&
            jobCenterX <= selectionRect.right &&
            jobCenterY >= selectionRect.top &&
            jobCenterY <= selectionRect.bottom) {
          lassoSelection.push(job.id);
        }
      });
      
      // Combine with existing selection if Ctrl/Cmd was held
      if (this.lassoSelection.ctrlKey) {
        this.selectedNodes = [...new Set([...initialSelection, ...lassoSelection])];
      } else {
        this.selectedNodes = lassoSelection;
      }
      
      // Clear single selection when we have multi-selection
      if (this.selectedNodes.length > 0) {
        this.selectedNode = null;
      }
      
      // Update single selected node for compatibility
      if (this.selectedNodes.length === 1) {
        this.selectedNode = this.selectedNodes[0];
      } else {
        this.selectedNode = null;
      }
    },
    startNodeDrag(event, job) {
      // Don't start node drag if we're trying to create a connection or editing
      if (event.target.closest('.connection-point')) return;
      if (this.editingNodeId === job.id) return;
      
      this.isDragging = true;
      this.draggedNode = job;
      
      // If the clicked node is selected, drag all selected nodes
      if (this.isNodeSelected(job.id)) {
        this.draggedNodes = this.jobs.filter(j => this.isNodeSelected(j.id));
      } else {
        // If not selected, only drag this node and select it
        this.draggedNodes = [job];
        this.selectedNodes = [job.id];
        this.selectedNode = job.id;
      }
      
      const canvas = this.$el.querySelector('.drop-zone');
      const canvasRect = canvas.getBoundingClientRect();
      
      // Calculate the offset from the mouse position to the job's position
      this.dragOffset = {
        x: event.clientX - canvasRect.left - job.x + canvas.scrollLeft,
        y: event.clientY - canvasRect.top - job.y + canvas.scrollTop
      };
      
      // Store initial positions of all dragged nodes in separate object
      this.dragInitialPositions = {};
      this.draggedNodes.forEach(node => {
        this.dragInitialPositions[node.id] = {
          x: node.x,
          y: node.y
        };
      });
      
      // Prevent text selection while dragging
      event.preventDefault();
      
      document.addEventListener('mousemove', this.handleNodeDrag);
      document.addEventListener('mouseup', this.stopNodeDrag);
    },
    handleNodeDrag(event) {
      if (this.isDragging && this.draggedNode) {
        const canvas = this.$el.querySelector('.drop-zone');
        const rect = canvas.getBoundingClientRect();
        
        // Calculate the new position for the primary dragged node
        const newX = event.clientX - rect.left - this.dragOffset.x + canvas.scrollLeft;
        const newY = event.clientY - rect.top - this.dragOffset.y + canvas.scrollTop;
        
        // Calculate the delta from the initial position
        const initialPos = this.dragInitialPositions[this.draggedNode.id];
        const deltaX = newX - initialPos.x;
        const deltaY = newY - initialPos.y;
        
        // Create position updates to emit (don't modify props directly)
        const updates = this.draggedNodes.map(node => {
          const nodeInitialPos = this.dragInitialPositions[node.id];
          return {
            id: node.id,
            x: Math.max(0, nodeInitialPos.x + deltaX),
            y: Math.max(0, nodeInitialPos.y + deltaY)
          };
        });
        
        // Emit position updates immediately for smooth dragging
        this.$emit('update-positions', updates);
      }
    },
    stopNodeDrag() {
      if (this.isDragging) {
        this.isDragging = false;
        // Clear drag state
        this.draggedNode = null;
        this.draggedNodes = [];
        this.dragInitialPositions = {};
      }
      document.removeEventListener('mousemove', this.handleNodeDrag);
      document.removeEventListener('mouseup', this.stopNodeDrag);
    },
    startConnection(event, nodeId, type) {
      if (type === 'out') {
        this.isConnecting = true;
        this.connectingFrom = nodeId;
        const node = this.jobs.find(j => j.id === nodeId);
        if (node) {
          const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256;
          const nodeHeight = this.nodeViewMode === 'compact' ? 40 : 50;
          this.tempConnection.x1 = node.x + nodeWidth; // Center of node
          this.tempConnection.y1 = node.y + nodeHeight; // Bottom of node
          this.tempConnection.x2 = this.tempConnection.x1;
          this.tempConnection.y2 = this.tempConnection.y1;
        }
        
        document.addEventListener('mousemove', this.handleConnectionDrag);
        document.addEventListener('mouseup', this.stopConnection);
      }
    },
    handleConnectionDrag(event) {
      if (this.isConnecting) {
        const canvas = this.$el.querySelector('.drop-zone');
        const rect = canvas.getBoundingClientRect();
        // Account for canvas transform
        this.tempConnection.x2 = (event.clientX - rect.left - this.canvasTransform.x) / this.zoom;
        this.tempConnection.y2 = (event.clientY - rect.top - this.canvasTransform.y) / this.zoom;
      }
    },
    stopConnection(event) {
      if (this.isConnecting) {
        // Check if we're over a node's input connection point
        const element = document.elementFromPoint(event.clientX, event.clientY);
        if (element && element.parentElement) {
          const nodeElement = element.parentElement.closest('.job-node');
          if (nodeElement) {
            // Find the node by checking the actual position rather than text content
            // This avoids issues with duplicate names or substring matches
            const nodeStyle = nodeElement.style;
            const nodeX = parseInt(nodeStyle.left);
            const nodeY = parseInt(nodeStyle.top);
            
            // Find the node that matches this exact position
            const toNode = this.jobs.find(j => j.x === nodeX && j.y === nodeY);
            
            if (toNode && toNode.id !== this.connectingFrom) {
              this.$emit('add-connection', {
                from: this.connectingFrom,
                to: toNode.id
              });
            }
          }
        }
        
        this.isConnecting = false;
        this.connectingFrom = null;
        document.removeEventListener('mousemove', this.handleConnectionDrag);
        document.removeEventListener('mouseup', this.stopConnection);
      }
    },
    getConnectionPath(connection) {
      const fromNode = this.jobs.find(j => j.id === connection.from);
      const toNode = this.jobs.find(j => j.id === connection.to);
      
      if (fromNode && toNode) {
        // Adjust node dimensions based on view mode
        const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256; // w-48 = 192px, w-64 = 256px
        const nodeHeight = this.nodeViewMode === 'compact' ? 40 : 50;
        
        // Connection points
        const x1 = (fromNode.x || 0) + nodeWidth / 2;
        const y1 = (fromNode.y || 0) + nodeHeight;
        const x2 = (toNode.x || 0) + nodeWidth / 2;
        const y2 = (toNode.y || 0);
        
        const dx = x2 - x1;
        const dy = y2 - y1;
        
        // For upward connections (negative dy), adjust the end point to stop before the node
        const arrowOffset = 5;
        const adjustedY2 = dy < 0 ? y2 + arrowOffset : y2 - arrowOffset;
        
        // Check if there are nodes between source and target that we need to avoid
        const obstacleNodes = this.jobs.filter(job => {
          if (job.id === fromNode.id || job.id === toNode.id) return false;
          
          const jobX = job.x || 0;
          const jobY = job.y || 0;
          
          // Check if this node is in the path between source and target
          const minX = Math.min(x1, x2) - nodeWidth / 2;
          const maxX = Math.max(x1, x2) + nodeWidth / 2;
          const minY = Math.min(y1, adjustedY2);
          const maxY = Math.max(y1, adjustedY2);
          
          return jobX + nodeWidth > minX && jobX < maxX && 
                 jobY + nodeHeight > minY && jobY < maxY;
        });
        
        // If there are obstacles and significant horizontal distance, route around them
        if (obstacleNodes.length > 0 && Math.abs(dx) > 100) {
          // Create a path that goes around obstacles
          const midY = (y1 + adjustedY2) / 2;
          
          // Determine which side to route around based on position
          const routeLeft = x1 < x2;
          const avoidanceOffset = nodeWidth + 60; // Space to clear around nodes
          
          // Find the extreme edge we need to avoid
          let extremeX = x1;
          obstacleNodes.forEach(node => {
            const nodeX = node.x || 0;
            if (routeLeft) {
              extremeX = Math.min(extremeX, nodeX - avoidanceOffset);
            } else {
              extremeX = Math.max(extremeX, nodeX + nodeWidth + avoidanceOffset);
            }
          });
          
          // Create a path with multiple control points that routes around obstacles
          if (Math.abs(dy) > 200) {
            // For long vertical distances, create a smooth S-curve around obstacles
            const cp1x = routeLeft ? Math.min(x1 - avoidanceOffset, extremeX) : Math.max(x1 + avoidanceOffset, extremeX);
            const cp1y = y1 + dy * 0.3;
            const cp2x = cp1x;
            const cp2y = adjustedY2 - dy * 0.3;
            
            return `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${adjustedY2}`;
          } else {
            // For shorter distances, use a gentler curve
            const offsetX = routeLeft ? -avoidanceOffset : avoidanceOffset;
            return `M ${x1} ${y1} C ${x1 + offsetX} ${midY}, ${x2 + offsetX} ${midY}, ${x2} ${adjustedY2}`;
          }
        }
        
        // Default smooth curve for non-problematic connections
        if (Math.abs(dy) < 40) {
          // Horizontal or nearly horizontal connection
          const midY = (y1 + adjustedY2) / 2;
          const horizontalOffset = dx !== 0 ? Math.sign(dx) * 20 : 20;
          return `M ${x1} ${y1} C ${x1 + horizontalOffset} ${midY}, ${x2 - horizontalOffset} ${midY}, ${x2} ${adjustedY2}`;
        }
        
        // Vertical connections with nice bezier curves
        const controlPointOffset = Math.max(30, Math.min(Math.abs(dy) * 0.4, 100));
        return `M ${x1} ${y1} C ${x1} ${y1 + controlPointOffset}, ${x2} ${adjustedY2 - controlPointOffset}, ${x2} ${adjustedY2}`;
      }
      return '';
    },
    getConnectionMidpoint(connection) {
      const fromNode = this.jobs.find(j => j.id === connection.from);
      const toNode = this.jobs.find(j => j.id === connection.to);
      
      if (fromNode && toNode) {
        const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256;
        const nodeHeight = this.nodeViewMode === 'compact' ? 40 : 50;
        const x1 = fromNode.x + nodeWidth;
        const y1 = fromNode.y + nodeHeight;
        const x2 = toNode.x + nodeWidth;
        const y2 = toNode.y;
        
        // Calculate the midpoint of the curve
        const t = 0.5; // midpoint parameter
        const cx1 = x1;
        const cy1 = y1 + (y2 - y1) * 0.3;
        const cx2 = x2;
        const cy2 = y2 - (y2 - y1) * 0.3;
        
        // Bezier curve formula for midpoint
        const mt = 1 - t;
        const x = mt * mt * mt * x1 + 3 * mt * mt * t * cx1 + 3 * mt * t * t * cx2 + t * t * t * x2;
        const y = mt * mt * mt * y1 + 3 * mt * mt * t * cy1 + 3 * mt * t * t * cy2 + t * t * t * y2;
        
        return { x, y };
      }
      return { x: 0, y: 0 };
    },
    zoomIn() {
      this.zoomCanvas(1.2);
    },
    zoomOut() {
      this.zoomCanvas(0.8);
    },
    fitToScreen() {
      // Calculate bounding box of all nodes
      if (this.jobs.length === 0) {
        this.zoom = 1;
        this.canvasTransform = { x: 0, y: 0 };
        return;
      }
      
      let minX = Infinity, minY = Infinity;
      let maxX = -Infinity, maxY = -Infinity;
      
      this.jobs.forEach(job => {
        const x = job.x !== undefined ? job.x : 100;
        const y = job.y !== undefined ? job.y : 100;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x + 180); // Use actual node width
        maxY = Math.max(maxY, y + 80);  // Use actual node height
      });
      
      // Handle case where all nodes are at same position
      if (minX === maxX) {
        maxX = minX + 180;
      }
      if (minY === maxY) {
        maxY = minY + 80;
      }
      
      const canvas = this.$el.querySelector('.drop-zone');
      if (!canvas) return;
      
      const rect = canvas.getBoundingClientRect();
      const padding = 80; // Increased padding for better visibility
      
      const contentWidth = maxX - minX + padding * 2;
      const contentHeight = maxY - minY + padding * 2;
      
      const scaleX = rect.width / contentWidth;
      const scaleY = rect.height / contentHeight;
      const newZoom = Math.min(scaleX, scaleY, 1.2); // Reduced max zoom for better visibility
      
      this.zoom = Math.max(0.3, newZoom); // Ensure minimum zoom
      this.canvasTransform = {
        x: (rect.width - contentWidth * this.zoom) / 2 + padding * this.zoom - minX * this.zoom,
        y: (rect.height - contentHeight * this.zoom) / 2 + padding * this.zoom - minY * this.zoom
      };
    },
    resetView() {
      this.zoom = 1;
      this.canvasTransform = { x: 0, y: 0 };
    },
    toggleGrid() {
      this.showGrid = !this.showGrid;
      // Save preference
      localStorage.setItem('canvas-showGrid', this.showGrid);
    },
    toggleSnapToGrid() {
      this.snapToGrid = !this.snapToGrid;
      // Save preference
      localStorage.setItem('canvas-snapToGrid', this.snapToGrid);
    },
    toggleAutoReflow() {
      this.autoReflowEnabled = !this.autoReflowEnabled;
      // Save preference
      localStorage.setItem('canvas-autoReflow', this.autoReflowEnabled);
    },
    togglePanTool() {
      this.panToolActive = !this.panToolActive;
      // Clear any ongoing operations
      if (this.panToolActive) {
        this.clearSelection();
        this.isLassoSelecting = false;
      }
    },
    getGridStyle() {
      const isDark = this.theme && (this.theme.name === 'Dark' || this.theme.name === 'Midnight');
      const color = isDark ? '255, 255, 255' : '0, 0, 0';
      
      return {
        backgroundImage: `linear-gradient(rgba(${color}, 0.03) 1px, transparent 1px),
                         linear-gradient(90deg, rgba(${color}, 0.03) 1px, transparent 1px),
                         linear-gradient(rgba(${color}, 0.08) 2px, transparent 2px),
                         linear-gradient(90deg, rgba(${color}, 0.08) 2px, transparent 2px)`,
        backgroundSize: `${this.gridSize}px ${this.gridSize}px, ${this.gridSize}px ${this.gridSize}px, ${this.gridSize * 5}px ${this.gridSize * 5}px, ${this.gridSize * 5}px ${this.gridSize * 5}px`,
        backgroundPosition: `${this.canvasTransform.x % (this.gridSize * 5)}px ${this.canvasTransform.y % (this.gridSize * 5)}px`
      };
    },
    setupResizeObserver() {
      const canvas = this.$el.querySelector('.drop-zone');
      if (!canvas) return;
      
      this.resizeObserver = new ResizeObserver((entries) => {
        for (let entry of entries) {
          const { width, height } = entry.contentRect;
          
          // Check if size actually changed significantly (more than 50px)
          const widthChanged = Math.abs(this.canvasWidth - width) > 50;
          const heightChanged = Math.abs(this.canvasHeight - height) > 50;
          
          if (widthChanged || heightChanged) {
            const oldWidth = this.canvasWidth;
            this.canvasWidth = width;
            this.canvasHeight = height;
            
            // Only reflow if canvas got smaller or significantly different
            if (width < oldWidth - 100 || widthChanged) {
              this.handleCanvasResize();
            }
          }
        }
      });
      
      this.resizeObserver.observe(canvas);
      
      // Get initial dimensions
      this.canvasWidth = canvas.offsetWidth;
      this.canvasHeight = canvas.offsetHeight;
    },
    handleCanvasResize() {
      // Don't reflow if disabled or if there are no jobs or user is actively working
      if (!this.autoReflowEnabled || this.jobs.length === 0 || this.isDragging || this.isConnecting || this.editingNodeId) {
        return;
      }
      
      // Check if any nodes are outside the new canvas bounds
      const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256;
      const nodeHeight = this.nodeViewMode === 'compact' ? 50 : 80;
      const padding = 50; // Increased padding for better visibility
      
      // Calculate safe boundaries - ensure nodes are fully visible
      const maxX = this.canvasWidth - nodeWidth - padding;
      const maxY = this.canvasHeight - nodeHeight - padding;
      
      let needsReflow = false;
      this.jobs.forEach(job => {
        // Check if any part of the node would be hidden
        const nodeRight = (job.x || 0) + nodeWidth;
        const nodeBottom = (job.y || 0) + nodeHeight;
        
        if ((job.x || 0) > maxX || nodeRight > this.canvasWidth - padding || 
            (job.y || 0) > maxY || nodeBottom > this.canvasHeight - padding) {
          needsReflow = true;
        }
      });
      
      // If nodes are outside bounds, trigger smart reflow
      if (needsReflow) {
        // Add a small delay to ensure canvas dimensions are fully updated
        setTimeout(() => {
          this.reflowToFitCanvas();
        }, 100);
      }
    },
    reflowToFitCanvas() {
      // Use the current layout algorithm but with new canvas dimensions
      const graph = this.buildGraph();
      const analysis = this.analyzeWorkflow(graph);
      
      // Store current zoom and transform
      const currentZoom = this.zoom;
      const currentTransform = { ...this.canvasTransform };
      
      // Determine which layout to use based on workflow structure
      if (analysis.isLinear) {
        this.arrangeLinearWorkflow(graph);
      } else if (analysis.isTree) {
        // Use horizontal tree for narrow spaces
        if (this.canvasWidth < 800) {
          this.autoArrangeTreeHorizontal();
        } else {
          this.autoArrangeTree();
        }
      } else {
        // Use hierarchy for complex workflows
        this.autoArrangeHierarchy();
      }
      
      // Optionally fit to screen after reflow
      if (this.canvasWidth < 600) {
        this.fitToScreen();
      } else {
        // Restore zoom and transform
        this.zoom = currentZoom;
        this.canvasTransform = currentTransform;
      }
    },
    showContextMenu(event) {
      // Canvas context menu (empty space)
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      this.menuPosition = {
        x: event.clientX - rect.left + canvas.scrollLeft,
        y: event.clientY - rect.top + canvas.scrollTop
      };
      this.menuType = 'canvas';
      this.menuTarget = null;
      this.showMenu = true;
      
      // Force Vue to recalculate hasClipboard
      this.$forceUpdate();
    },
    showNodeContextMenu(event, node) {
      // Node-specific context menu
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      this.menuPosition = {
        x: event.clientX - rect.left + canvas.scrollLeft,
        y: event.clientY - rect.top + canvas.scrollTop
      };
      this.menuType = 'node';
      this.menuTarget = node;
      this.showMenu = true;
      
      // Select the node if not already selected
      if (!this.isNodeSelected(node.id)) {
        this.selectedNodes = [node.id];
        this.selectedNode = node.id;
      }
    },
    showConnectionContextMenu(event, connection) {
      // Connection-specific context menu
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      this.menuPosition = {
        x: event.clientX - rect.left + canvas.scrollLeft,
        y: event.clientY - rect.top + canvas.scrollTop
      };
      this.menuType = 'connection';
      this.menuTarget = connection;
      this.showMenu = true;
    },
    hideContextMenu() {
      this.showMenu = false;
      this.menuType = null;
      this.menuTarget = null;
    },
    hideMenus(event) {
      // Hide context menu if clicking outside
      if (!event.target.closest('.context-menu')) {
        this.hideContextMenu();
      }
      // Hide arrange menu if clicking outside
      if (!event.target.closest('.relative')) {
        this.showArrangeMenu = false;
      }
    },
    autoArrangeDefault() {
      // Default to layered layout since it works best for most DAG workflows
      this.autoArrangeHierarchy();
    },
    analyzeWorkflow(graph) {
      const analysis = {
        isLinear: false,
        isTree: false,
        hasMultiplePaths: false,
        hasNoConnections: graph.edges.length === 0,
        maxFanOut: 0,
        maxFanIn: 0,
        longestPath: 0
      };
      
      if (analysis.hasNoConnections) return analysis;
      
      // Check if it's linear (each node has at most 1 in and 1 out)
      let isLinear = true;
      let maxFanOut = 0;
      let maxFanIn = 0;
      
      this.jobs.forEach(job => {
        const fanOut = graph.outDegree[job.id] || 0;
        const fanIn = graph.inDegree[job.id] || 0;
        maxFanOut = Math.max(maxFanOut, fanOut);
        maxFanIn = Math.max(maxFanIn, fanIn);
        
        if ((fanIn > 1 && graph.inDegree[job.id] > 0) || fanOut > 1) {
          isLinear = false;
        }
      });
      
      analysis.isLinear = isLinear;
      analysis.maxFanOut = maxFanOut;
      analysis.maxFanIn = maxFanIn;
      
      // Check if it's a tree (no node has multiple parents)
      analysis.isTree = maxFanIn <= 1 && !isLinear;
      
      // Check for multiple paths (diamond patterns, reconvergence)
      analysis.hasMultiplePaths = maxFanIn > 1;
      
      return analysis;
    },
    arrangeLinearWorkflow(graph) {
      // Arrange linear workflows in a snake/zigzag pattern to save space
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256;
      // Ensure minimum spacing to prevent overlapping
      const minHorizontalSpacing = nodeWidth + 40;
      const horizontalSpacing = this.nodeViewMode === 'compact' ? 
        Math.max(minHorizontalSpacing, 250) : 
        Math.max(minHorizontalSpacing, 320);
      const verticalSpacing = this.nodeViewMode === 'compact' ? 100 : 120;
      const padding = 50;
      const effectiveWidth = canvasWidth - padding * 2;
      const nodesPerRow = Math.max(1, Math.floor(effectiveWidth / horizontalSpacing));
      
      // Find the start node(s)
      const starts = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      const positioned = new Set();
      let currentX = 50;
      let currentY = 50;
      let direction = 1; // 1 for right, -1 for left
      let nodeCount = 0;
      
      const positionChain = (nodeId) => {
        if (positioned.has(nodeId)) return;
        positioned.add(nodeId);
        
        const job = this.jobs.find(j => j.id === nodeId);
        if (!job) return;
        
        job.x = currentX;
        job.y = currentY;
        
        nodeCount++;
        
        // Move to next position
        if (nodeCount % nodesPerRow === 0) {
          // Move to next row
          currentY += verticalSpacing;
          direction *= -1; // Change direction
          currentX = direction === 1 ? 50 : canvasWidth - 200;
        } else {
          // Move horizontally
          currentX += horizontalSpacing * direction;
        }
        
        // Position next in chain
        const next = graph.edges.find(e => e.from === nodeId);
        if (next) {
          positionChain(next.to);
        }
      };
      
      starts.forEach(start => positionChain(start.id));
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
    },
    arrangeComplexDAG(graph, analysis) {
      // For complex DAGs, group related nodes and minimize crossings
      const layers = this.assignLayers(graph);
      const groups = this.identifyGroups(graph);
      
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const verticalSpacing = this.nodeViewMode === 'compact' ? 100 : 120;
      const horizontalSpacing = this.nodeViewMode === 'compact' ? 250 : 300;
      const padding = 80;
      
      // Position each layer with group awareness
      layers.forEach((layer, layerIndex) => {
        if (layer.length === 1) {
          // Center single nodes
          const job = this.jobs.find(j => j.id === layer[0]);
          if (job) {
            job.x = canvasWidth / 2 - 64;
            job.y = padding + layerIndex * verticalSpacing;
          }
        } else {
          // Group nodes that share dependencies
          const groupedNodes = this.groupNodesInLayer(layer, groups, graph);
          let currentX = padding;
          
          groupedNodes.forEach((group, groupIndex) => {
            // Add spacing between groups
            if (groupIndex > 0) currentX += 50;
            
            group.forEach((nodeId, index) => {
              const job = this.jobs.find(j => j.id === nodeId);
              if (job) {
                job.x = currentX + index * horizontalSpacing;
                job.y = padding + layerIndex * verticalSpacing;
              }
            });
            
            currentX += group.length * horizontalSpacing;
          });
        }
      });
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
    },
    identifyGroups(graph) {
      // Identify groups of nodes that work together
      const groups = new Map();
      let groupId = 0;
      
      // Group nodes that share common parents or children
      this.jobs.forEach(job => {
        if (!groups.has(job.id)) {
          const group = new Set([job.id]);
          
          // Find nodes with same parents
          const parents = graph.edges.filter(e => e.to === job.id).map(e => e.from);
          const siblings = graph.edges
            .filter(e => parents.includes(e.from))
            .map(e => e.to)
            .filter(id => id !== job.id);
          
          siblings.forEach(sibling => group.add(sibling));
          
          // Assign group ID to all members
          group.forEach(member => groups.set(member, groupId));
          groupId++;
        }
      });
      
      return groups;
    },
    groupNodesInLayer(layer, groups, graph) {
      // Group nodes in a layer based on their relationships
      const nodeGroups = new Map();
      
      layer.forEach(nodeId => {
        const groupId = groups.get(nodeId) || nodeId;
        if (!nodeGroups.has(groupId)) {
          nodeGroups.set(groupId, []);
        }
        nodeGroups.get(groupId).push(nodeId);
      });
      
      // Sort groups to minimize crossings
      const sortedGroups = Array.from(nodeGroups.values()).sort((a, b) => {
        // Sort by average position of parents
        const avgPosA = this.getAverageParentPosition(a, graph);
        const avgPosB = this.getAverageParentPosition(b, graph);
        return avgPosA - avgPosB;
      });
      
      return sortedGroups;
    },
    getAverageParentPosition(nodeIds, graph) {
      const parentPositions = [];
      
      nodeIds.forEach(nodeId => {
        const parents = graph.edges.filter(e => e.to === nodeId).map(e => e.from);
        parents.forEach(parentId => {
          const parent = this.jobs.find(j => j.id === parentId);
          if (parent && parent.x !== undefined) {
            parentPositions.push(parent.x);
          }
        });
      });
      
      if (parentPositions.length === 0) return 0;
      return parentPositions.reduce((sum, x) => sum + x, 0) / parentPositions.length;
    },
    arrangeUnconnectedNodes() {
      // Arrange unconnected nodes in a more pleasing pattern
      const nodeCount = this.jobs.length;
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const canvasHeight = this.$el.querySelector('.drop-zone').offsetHeight;
      const padding = 100;
      
      if (nodeCount <= 3) {
        // Horizontal line for small counts
        const spacing = Math.min(200, (canvasWidth - 2 * padding) / (nodeCount + 1));
        const y = canvasHeight / 3;
        this.jobs.forEach((job, index) => {
          job.x = padding + (index + 1) * spacing;
          job.y = y;
        });
      } else if (nodeCount <= 8) {
        // Diamond or hexagon pattern
        const centerX = canvasWidth / 2;
        const centerY = canvasHeight / 2;
        const radius = Math.min(200, (Math.min(canvasWidth, canvasHeight) - 2 * padding) / 3);
        const angleStep = (2 * Math.PI) / nodeCount;
        
        this.jobs.forEach((job, index) => {
          const angle = index * angleStep - Math.PI / 2;
          job.x = centerX + radius * Math.cos(angle) - 64;
          job.y = centerY + radius * Math.sin(angle) - 18;
        });
      } else {
        // Spiral pattern for many nodes
        const centerX = canvasWidth / 2;
        const centerY = canvasHeight / 2;
        const angleStep = Math.PI / 4; // 45 degrees
        let radius = 100;
        let angle = 0;
        const radiusIncrement = 30;
        
        this.jobs.forEach((job, index) => {
          job.x = centerX + radius * Math.cos(angle) - 64;
          job.y = centerY + radius * Math.sin(angle) - 18;
          
          angle += angleStep;
          if (angle >= 2 * Math.PI) {
            angle = 0;
            radius += radiusIncrement;
          }
        });
      }
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
    },
    autoArrangeHierarchy() {
      // Sugiyama-style layered graph layout with improved convergence point positioning
      const graph = this.buildGraph();
      const layers = this.assignLayers(graph);
      const orderedLayers = this.minimizeCrossings(layers, graph);
      
      // Position jobs based on optimized layers - use more canvas space
      const nodeWidth = this.nodeViewMode === 'compact' ? 192 : 256;
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const canvasHeight = this.$el.querySelector('.drop-zone').offsetHeight;
      
      // Dynamically calculate spacing based on canvas size and number of layers/nodes
      const maxNodesInLayer = Math.max(...orderedLayers.map(layer => layer.length));
      const numLayers = orderedLayers.length;
      
      // Use more of the available space
      const padding = 60;
      const effectiveWidth = canvasWidth - padding * 2;
      const effectiveHeight = canvasHeight - padding * 2;
      
      // Calculate optimal spacing with minimum values to prevent overlapping
      // Minimum spacing must be at least node width + gap
      const minHorizontalSpacing = nodeWidth + 40; // Add 40px gap between nodes
      const horizontalSpacing = maxNodesInLayer > 1 ? 
        Math.max(minHorizontalSpacing, Math.min(400, effectiveWidth / maxNodesInLayer)) : 
        minHorizontalSpacing;
      // Ensure minimum vertical spacing of 120px so connection lines are always visible
      // Don't compress below this even if it means scrolling
      const minVerticalSpacing = 120;
      const idealVerticalSpacing = numLayers > 1 ? effectiveHeight / numLayers : 150;
      const verticalSpacing = Math.max(minVerticalSpacing, Math.min(180, idealVerticalSpacing));
      
      const startY = padding;
      
      // First pass: position all nodes
      orderedLayers.forEach((layer, layerIndex) => {
        // Calculate the actual spacing for this layer
        let actualSpacing;
        let startX;
        
        if (layer.length === 1) {
          // Single node - center it
          startX = (canvasWidth - nodeWidth) / 2;
        } else {
          // Multiple nodes - ensure they don't overlap
          const minSpacing = nodeWidth + 40; // Minimum gap between nodes
          const availableWidth = effectiveWidth;
          const neededWidth = layer.length * nodeWidth + (layer.length - 1) * 40;
          
          if (neededWidth <= availableWidth) {
            // We have enough space - spread them evenly
            actualSpacing = (availableWidth - nodeWidth) / (layer.length - 1);
            actualSpacing = Math.min(actualSpacing, 350); // Don't spread too far
          } else {
            // Not enough space - use minimum spacing and allow horizontal scroll
            actualSpacing = minSpacing;
          }
          
          // Center the layer if possible
          const totalWidth = nodeWidth + (layer.length - 1) * actualSpacing;
          startX = Math.max(padding, (canvasWidth - totalWidth) / 2);
        }
        
        layer.forEach((jobId, index) => {
          const job = this.jobs.find(j => j.id === jobId);
          if (job) {
            if (layer.length === 1) {
              job.x = startX;
            } else {
              job.x = startX + index * actualSpacing;
            }
            job.y = startY + layerIndex * verticalSpacing;
          }
        });
      });
      
      // Second pass: optimize positions for better clarity
      // 1. Separate parallel chains
      // 2. Center convergence points under their dependencies
      orderedLayers.forEach((layer, layerIndex) => {
        // Group nodes by their dependency chains
        const chains = new Map();
        
        layer.forEach(jobId => {
          // Find which chain this node belongs to by tracing back to roots
          const chainRoot = this.findChainRoot(jobId, graph);
          if (!chains.has(chainRoot)) {
            chains.set(chainRoot, []);
          }
          chains.get(chainRoot).push(jobId);
        });
        
        // If we have multiple chains in this layer, separate them
        if (chains.size > 1 && layer.length > 1) {
          const chainArray = Array.from(chains.entries());
          const totalChains = chainArray.length;
          const availableWidth = canvasWidth - padding * 2;
          const chainSpacing = availableWidth / (totalChains + 1);
          
          chainArray.forEach(([root, nodes], chainIndex) => {
            const chainX = padding + chainSpacing * (chainIndex + 1) - nodeWidth / 2;
            nodes.forEach((nodeId, nodeIndex) => {
              const job = this.jobs.find(j => j.id === nodeId);
              if (job) {
                // Position nodes in this chain close together
                job.x = chainX + nodeIndex * (nodeWidth + 20);
              }
            });
          });
        }
        
        // Position convergence points (nodes with multiple incoming connections)
        layer.forEach(jobId => {
          const incomingCount = graph.inDegree[jobId] || 0;
          
          if (incomingCount > 1) {
            const job = this.jobs.find(j => j.id === jobId);
            if (job) {
              // Find all parent nodes
              const parents = [];
              graph.edges.forEach(edge => {
                if (edge.to === jobId) {
                  const parentJob = this.jobs.find(j => j.id === edge.from);
                  if (parentJob) {
                    parents.push(parentJob);
                  }
                }
              });
              
              // For convergence points, center them between the extremes of their parents
              if (parents.length > 0) {
                const minX = Math.min(...parents.map(p => p.x));
                const maxX = Math.max(...parents.map(p => p.x));
                const centerX = (minX + maxX) / 2;
                
                // Check if this position would cause overlap
                let canMove = true;
                layer.forEach(otherId => {
                  if (otherId !== jobId) {
                    const otherJob = this.jobs.find(j => j.id === otherId);
                    if (otherJob) {
                      const distance = Math.abs(centerX - otherJob.x);
                      if (distance < nodeWidth + 40) {
                        canMove = false;
                      }
                    }
                  }
                });
                
                if (canMove) {
                  job.x = centerX;
                }
              }
            }
          }
        });
      });
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
    },
    buildGraph() {
      const graph = {
        nodes: new Set(this.jobs.map(j => j.id)),
        edges: [],
        inDegree: {},
        outDegree: {}
      };
      
      // Initialize degrees
      this.jobs.forEach(job => {
        graph.inDegree[job.id] = 0;
        graph.outDegree[job.id] = 0;
      });
      
      // Build edges and calculate degrees
      this.jobs.forEach(job => {
        if (job.dependencies) {
          job.dependencies.forEach(dep => {
            graph.edges.push({ from: dep, to: job.id });
            graph.outDegree[dep] = (graph.outDegree[dep] || 0) + 1;
            graph.inDegree[job.id]++;
          });
        }
      });
      
      return graph;
    },
    findChainRoot(nodeId, graph, visited = new Set()) {
      // Trace back to find the root of the dependency chain
      if (visited.has(nodeId)) return nodeId;
      visited.add(nodeId);
      
      // If this is a root node (no incoming edges), return it
      if (graph.inDegree[nodeId] === 0) {
        return nodeId;
      }
      
      // Find the first parent and trace back
      const parent = graph.edges.find(e => e.to === nodeId);
      if (parent) {
        return this.findChainRoot(parent.from, graph, visited);
      }
      
      return nodeId;
    },
    assignLayers(graph) {
      const layers = [];
      const level = {};
      const visited = new Set();
      
      // Find roots (nodes with no dependencies)
      const roots = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      
      // First, calculate the longest path to each node
      // This ensures nodes are placed after ALL their dependencies
      const calculateLevel = (nodeId) => {
        if (level[nodeId] !== undefined) {
          return level[nodeId];
        }
        
        // Find all nodes that this node depends on
        const dependencies = graph.edges
          .filter(e => e.to === nodeId)
          .map(e => e.from);
        
        if (dependencies.length === 0) {
          level[nodeId] = 0; // Root node
        } else {
          // Place this node one level after its furthest dependency
          level[nodeId] = Math.max(...dependencies.map(dep => calculateLevel(dep))) + 1;
        }
        
        return level[nodeId];
      };
      
      // Calculate level for all nodes
      this.jobs.forEach(job => {
        calculateLevel(job.id);
      });
      
      // Assign nodes to layers based on calculated levels
      this.jobs.forEach(job => {
        const layer = level[job.id];
        if (!layers[layer]) {
          layers[layer] = [];
        }
        layers[layer].push(job.id);
      });
      
      return layers;
    },
    minimizeCrossings(layers, graph) {
      // Simple barycentric method to minimize edge crossings
      const optimizedLayers = layers.map(layer => [...layer]);
      
      // Iterate through layers to minimize crossings
      for (let iter = 0; iter < 10; iter++) {
        let improved = false;
        
        for (let i = 1; i < optimizedLayers.length; i++) {
          const positions = {};
          
          // Calculate barycentric positions
          optimizedLayers[i].forEach(node => {
            const predecessors = graph.edges
              .filter(e => e.to === node)
              .map(e => e.from)
              .filter(pred => optimizedLayers[i - 1].includes(pred));
            
            if (predecessors.length > 0) {
              const avgPos = predecessors.reduce((sum, pred) => {
                return sum + optimizedLayers[i - 1].indexOf(pred);
              }, 0) / predecessors.length;
              positions[node] = avgPos;
            } else {
              positions[node] = optimizedLayers[i].indexOf(node);
            }
          });
          
          // Sort layer by barycentric positions
          const sorted = [...optimizedLayers[i]].sort((a, b) => positions[a] - positions[b]);
          
          if (JSON.stringify(sorted) !== JSON.stringify(optimizedLayers[i])) {
            optimizedLayers[i] = sorted;
            improved = true;
          }
        }
        
        if (!improved) break;
      }
      
      return optimizedLayers;
    },
    getMaxDepth(graph) {
      // Calculate the maximum depth of the DAG
      const depths = {};
      const visited = new Set();
      
      const calculateDepth = (nodeId) => {
        if (visited.has(nodeId)) return depths[nodeId] || 0;
        visited.add(nodeId);
        
        const children = graph.edges.filter(e => e.from === nodeId).map(e => e.to);
        if (children.length === 0) {
          depths[nodeId] = 1;
        } else {
          depths[nodeId] = 1 + Math.max(...children.map(child => calculateDepth(child)));
        }
        
        return depths[nodeId];
      };
      
      const roots = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      const maxDepth = Math.max(...roots.map(root => calculateDepth(root.id)));
      return maxDepth || 1;
    },
    autoArrangeTree() {
      // Tree layout for hierarchical data
      const graph = this.buildGraph();
      const roots = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      
      if (roots.length === 0) {
        // If no roots, fall back to hierarchy layout
        this.autoArrangeHierarchy();
        return;
      }
      
      const positioned = new Set();
      const nodeWidth = this.nodeViewMode === 'compact' ? 200 : 260;
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const canvasHeight = this.$el.querySelector('.drop-zone').offsetHeight;
      
      // Use more vertical space for tree layout with minimum spacing
      // Ensure minimum of 120px between levels so connection lines are visible
      const levelHeight = Math.max(120, Math.min(160, (canvasHeight - 100) / this.getMaxDepth(graph)));
      const padding = 60;
      let currentX = padding;
      
      // If multiple roots, space them evenly
      if (roots.length > 1) {
        const spacing = (canvasWidth - padding * 2) / roots.length;
        roots.forEach((root, index) => {
          const centerX = padding + spacing * index + spacing / 2 - nodeWidth / 2;
          this.layoutTree(root.id, graph, positioned, centerX, padding, nodeWidth, levelHeight);
        });
      } else {
        // Single root - center it
        const centerX = (canvasWidth - nodeWidth) / 2;
        this.layoutTree(roots[0].id, graph, positioned, centerX, padding, nodeWidth, levelHeight);
      }
      
      // Ensure all nodes are within visible bounds
      this.jobs.forEach(job => {
        if (job.x + nodeWidth > canvasWidth - padding) {
          job.x = canvasWidth - nodeWidth - padding;
        }
      });
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
    },
    getTreeWidth(nodeId, graph, positioned, nodeWidth, levelHeight) {
      if (positioned.has(nodeId)) return 0;
      positioned.add(nodeId);
      
      const children = graph.edges
        .filter(e => e.from === nodeId)
        .map(e => e.to)
        .filter(child => !positioned.has(child));
      
      if (children.length === 0) {
        return nodeWidth;
      }
      
      let totalWidth = 0;
      children.forEach(child => {
        totalWidth += this.getTreeWidth(child, graph, positioned, nodeWidth, levelHeight);
      });
      
      // Add spacing between children scaled to node width
      const spacing = Math.max(60, nodeWidth * 0.3);
      totalWidth += spacing * (children.length - 1);
      
      return Math.max(nodeWidth, totalWidth);
    },
    layoutTree(nodeId, graph, positioned, x, y, nodeWidth, levelHeight) {
      if (positioned.has(nodeId)) return 0;
      positioned.add(nodeId);
      
      const job = this.jobs.find(j => j.id === nodeId);
      if (!job) return 0;
      
      // Get children
      const children = graph.edges
        .filter(e => e.from === nodeId)
        .map(e => e.to)
        .filter(child => !positioned.has(child));
      
      if (children.length === 0) {
        // Leaf node
        job.x = x;
        job.y = y;
        return nodeWidth;
      }
      
      // Layout children with better spacing to prevent overlapping
      const childSpacing = Math.max(60, nodeWidth * 0.3); // Space between child subtrees, scale with node width
      const childWidths = [];
      let totalWidth = 0;
      
      // First calculate all child widths
      children.forEach(child => {
        const tempPositioned = new Set(positioned);
        const childWidth = this.getTreeWidth(child, graph, tempPositioned, nodeWidth, levelHeight);
        childWidths.push(childWidth);
        totalWidth += childWidth;
      });
      
      // Add spacing between children
      totalWidth += childSpacing * (children.length - 1);
      
      // Position children
      let childX = x - totalWidth / 2 + nodeWidth / 2;
      children.forEach((child, index) => {
        this.layoutTree(child, graph, positioned, childX, y + levelHeight, nodeWidth, levelHeight);
        childX += childWidths[index] + childSpacing;
      });
      
      // Position parent node centered above children
      job.x = x;
      job.y = y;
      
      return Math.max(nodeWidth, totalWidth);
    },
    autoArrangeTreeHorizontal() {
      // Horizontal tree layout (left to right)
      const graph = this.buildGraph();
      const roots = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      
      if (roots.length === 0) {
        // If no roots, fall back to hierarchy layout
        this.autoArrangeHierarchy();
        return;
      }
      
      const positioned = new Set();
      const nodeWidth = this.nodeViewMode === 'compact' ? 200 : 260;
      const nodeHeight = this.nodeViewMode === 'compact' ? 60 : 80;
      const levelWidth = this.nodeViewMode === 'compact' ? 280 : 340;
      let currentY = 50;
      
      // Layout each tree horizontally
      roots.forEach(root => {
        const treeHeight = this.layoutTreeHorizontal(root.id, graph, positioned, 50, currentY, levelWidth, nodeHeight);
        currentY += treeHeight + 50;
      });
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
      this.showArrangeMenu = false;
    },
    layoutTreeHorizontal(nodeId, graph, positioned, x, y, levelWidth, nodeHeight) {
      if (positioned.has(nodeId)) return 0;
      positioned.add(nodeId);
      
      const job = this.jobs.find(j => j.id === nodeId);
      if (!job) return 0;
      
      // Get children
      const children = graph.edges
        .filter(e => e.from === nodeId)
        .map(e => e.to)
        .filter(child => !positioned.has(child));
      
      if (children.length === 0) {
        // Leaf node
        job.x = x;
        job.y = y;
        return nodeHeight;
      }
      
      // Layout children horizontally (left to right)
      let childY = y;
      let totalHeight = 0;
      
      children.forEach((child, index) => {
        const childHeight = this.layoutTreeHorizontal(child, graph, positioned, x + levelWidth, childY, levelWidth, nodeHeight);
        childY += childHeight + 20; // Add spacing between children
        totalHeight += childHeight + (index > 0 ? 20 : 0);
      });
      
      // Center parent node vertically relative to its children
      job.x = x;
      job.y = y + (totalHeight - nodeHeight) / 2;
      
      return totalHeight;
    },
    autoArrangeForce() {
      // Removed - use Auto-arrange instead
      this.autoArrangeDefault();
    },
    autoArrangeCircular() {
      // Removed - use Auto-arrange instead
      this.autoArrangeDefault();
    },
    autoArrangeGrid() {
      // Removed - use Auto-arrange instead
      this.autoArrangeDefault();
    },
    clearCanvas() {
      if (confirm('Are you sure you want to remove all jobs from the canvas?')) {
        this.$emit('clear-canvas');
      }
      this.hideContextMenu();
    },
    // Context menu actions for nodes
    renameNode() {
      if (this.menuTarget) {
        this.startInlineRename(this.menuTarget.id);
      }
      this.hideContextMenu();
    },
    startInlineRename(nodeId) {
      const node = this.jobs.find(j => j.id === nodeId);
      if (node) {
        this.editingNodeId = nodeId;
        this.editingNodeName = node.id;
        // Focus the input after Vue updates the DOM
        this.$nextTick(() => {
          const input = this.$refs[`renameInput-${nodeId}`];
          if (input) {
            input.focus();
            input.select();
          }
        });
      }
    },
    finishRename() {
      // Don't save if we cancelled with Escape
      if (this.renameCancelled) {
        this.renameCancelled = false;
        return;
      }
      
      if (this.editingNodeId && this.editingNodeName && this.editingNodeName.trim()) {
        const node = this.jobs.find(j => j.id === this.editingNodeId);
        if (node && this.editingNodeName.trim() !== node.id) {
          this.$emit('rename-node', { node, newName: this.editingNodeName.trim() });
        }
      }
      this.editingNodeId = null;
      this.editingNodeName = '';
    },
    cancelRename() {
      this.renameCancelled = true;
      this.editingNodeId = null;
      this.editingNodeName = '';
    },
    editNodeProperties() {
      if (this.menuTarget) {
        this.$emit('edit-node', this.menuTarget);
      }
      this.hideContextMenu();
    },
    duplicateNode() {
      if (this.menuTarget) {
        // Pass the menu target directly - parent will handle the duplication
        this.$emit('duplicate-nodes', [this.menuTarget]);
      }
      this.hideContextMenu();
    },
    copyNode() {
      if (this.menuTarget) {
        // For a single node, don't include any connections
        // A single node can't have internal connections
        
        // Deep clone to avoid reference issues
        localStorage.setItem('canvas-clipboard', JSON.stringify({
          type: 'subgraph',
          nodes: [JSON.parse(JSON.stringify(this.menuTarget))],
          connections: [], // No connections for single node
          timestamp: Date.now()
        }));
        console.log('Node copied to clipboard (no connections):', this.menuTarget.id);
      }
      this.hideContextMenu();
    },
    cutNode() {
      if (this.menuTarget) {
        // For a single node, don't include any connections
        
        // Deep clone before deleting
        localStorage.setItem('canvas-clipboard', JSON.stringify({
          type: 'subgraph',
          nodes: [JSON.parse(JSON.stringify(this.menuTarget))],
          connections: [], // No connections for single node
          timestamp: Date.now()
        }));
        // Delete the node
        this.$emit('delete-nodes', [this.menuTarget.id]);
      }
      this.hideContextMenu();
    },
    deleteNode() {
      if (this.menuTarget) {
        this.$emit('delete-nodes', [this.menuTarget.id]);
      }
      this.hideContextMenu();
    },
    // Context menu actions for connections
    editConnectionProperties() {
      if (this.menuTarget) {
        this.$emit('edit-connection', this.menuTarget);
      }
      this.hideContextMenu();
    },
    deleteConnection() {
      if (this.menuTarget) {
        this.$emit('delete-connection', this.menuTarget);
      }
      this.hideContextMenu();
    },
    selectConnection(connection) {
      // Future: implement connection selection
      console.log('Connection selected:', connection);
    }
  },
  computed: {
    totalSelectedCount() {
      // Count total selected nodes from both selection types
      const uniqueSelected = new Set(this.selectedNodes);
      if (this.selectedNode && !uniqueSelected.has(this.selectedNode)) {
        uniqueSelected.add(this.selectedNode);
      }
      return uniqueSelected.size;
    },
    hasClipboard() {
      try {
        const clipboardData = localStorage.getItem('canvas-clipboard');
        return clipboardData !== null;
      } catch (e) {
        return false;
      }
    },
    canvasCursor() {
      if (this.isPanning) {
        return 'grabbing';
      } else if (this.panToolActive || this.spacePressed) {
        return 'grab';
      } else if (this.isLassoSelecting) {
        return 'crosshair';
      } else {
        return 'default';
      }
    }
  }
};
</script>

<style scoped>
.bg-grid-pattern {
  background-color: #fafafa;
  background-image: 
    linear-gradient(rgba(0, 0, 0, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.03) 1px, transparent 1px),
    linear-gradient(rgba(0, 0, 0, 0.08) 2px, transparent 2px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.08) 2px, transparent 2px);
  background-size: 20px 20px, 20px 20px, 100px 100px, 100px 100px;
  background-position: 0 0, 0 0, 0 0, 0 0;
}

.bg-grid-pattern-dark {
  background-color: transparent;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(rgba(255, 255, 255, 0.08) 2px, transparent 2px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.08) 2px, transparent 2px);
  background-size: 20px 20px, 20px 20px, 100px 100px, 100px 100px;
  background-position: 0 0, 0 0, 0 0, 0 0;
}
</style>