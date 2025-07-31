<template>
  <div class="h-full relative overflow-hidden" :class="theme ? theme.canvasBg : ''">
    <div class="absolute inset-0" :class="theme && theme.name === 'Dark' || theme && theme.name === 'Midnight' ? 'bg-grid-pattern-dark' : 'bg-grid-pattern'"></div>
    
    <!-- Canvas -->
    <div class="drop-zone relative h-full overflow-auto p-8"
         @drop.prevent="handleDrop"
         @dragover.prevent="handleDragOver"
         @dragleave="handleDragLeave"
         @contextmenu.prevent="showContextMenu">
      
      <!-- SVG for connections -->
      <svg class="absolute inset-0 pointer-events-none" style="width: 100%; height: 100%;">
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="10" 
                  refX="9" refY="5" orient="auto">
            <path d="M0,0 L0,10 L10,5 z" :fill="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'" />
          </marker>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
        
        <!-- Connection lines -->
        <g v-for="connection in connections" :key="`${connection.from}-${connection.to}`">
          <!-- Shadow/glow effect -->
          <path :d="getConnectionPath(connection)" 
                :stroke="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'"
                stroke-width="3" 
                fill="none"
                opacity="0.5"
                filter="url(#glow)" />
          <!-- Main connection line -->
          <path :d="getConnectionPath(connection)" 
                class="connection-line pointer-events-auto"
                :stroke="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'"
                @click="$emit('remove-connection', connection)"
                style="cursor: pointer" />
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
           :style="{ left: `${job.x}px`, top: `${job.y}px` }"
           class="job-node absolute rounded-md shadow border select-none transition-all"
           :class="[
             theme ? theme.nodeBg : 'bg-white',
             theme ? theme.border : 'border-gray-300',
             nodeViewMode === 'compact' ? 'p-2 w-32' : 'p-2.5 w-36',
             selectedNode === job.id ? (theme ? theme.nodeSelected : 'border-indigo-500 shadow-lg ring-2 ring-indigo-200') : (theme ? theme.nodeHover : 'hover:border-indigo-300'),
             { 'cursor-grabbing': isDragging && draggedNode && draggedNode.id === job.id, 
               'cursor-grab': !isDragging }
           ]"
           @mousedown="startNodeDrag($event, job)"
           @click="selectNode(job.id)">
        
        <!-- Connection points -->
        <div class="absolute -top-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 rounded-full cursor-pointer opacity-0 hover:opacity-100 transition-opacity"
             :class="[{ 'opacity-100': isConnecting || selectedNode === job.id }, theme ? theme.accent : 'bg-indigo-500']"
             @mousedown.stop="startConnection($event, job.id, 'in')"></div>
        <div class="absolute -bottom-1.5 left-1/2 transform -translate-x-1/2 w-3 h-3 rounded-full cursor-pointer opacity-0 hover:opacity-100 transition-opacity"
             :class="[{ 'opacity-100': isConnecting || selectedNode === job.id }, theme ? theme.accent : 'bg-indigo-500']"
             @mousedown.stop="startConnection($event, job.id, 'out')"></div>
        
        <!-- Job content -->
        <div class="flex items-center justify-between gap-1">
          <h3 class="font-medium truncate text-sm" :class="theme ? theme.text : 'text-gray-900'">{{ job.id }}</h3>
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
      <svg v-if="isConnecting" class="absolute inset-0 pointer-events-none" style="width: 100%; height: 100%;">
        <line :x1="tempConnection.x1" :y1="tempConnection.y1"
              :x2="tempConnection.x2" :y2="tempConnection.y2"
              :stroke="theme && theme.accent ? theme.accent.replace('bg-', '#').replace('indigo-600', '6366f1').replace('blue-600', '2563eb').replace('purple-600', '9333ea').replace('emerald-600', '059669') : '#6366f1'"
              stroke-width="2" stroke-dasharray="5,5" />
      </svg>
    </div>
    
    <!-- Canvas controls -->
    <div class="absolute bottom-4 right-4 flex flex-col space-y-2">
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
      
      <!-- Auto-arrange Button -->
      <button @click="autoArrangeTree" 
              class="px-4 py-2 rounded-lg shadow transition-colors" 
              :class="theme ? [theme.accent, theme.accentText, theme.accentHover] : 'bg-indigo-600 text-white hover:bg-indigo-700'"
              title="Auto-arrange (Tree Layout)">
        <i class="fas fa-tree mr-2"></i>Auto-arrange
      </button>
      
      <!-- Zoom Controls -->
      <div class="flex space-x-2">
        <button @click="zoomIn" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Zoom In">
          <i class="fas fa-search-plus"></i>
        </button>
        <button @click="zoomOut" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Zoom Out">
          <i class="fas fa-search-minus"></i>
        </button>
        <button @click="fitToScreen" 
                class="p-2 rounded-lg shadow transition-colors" 
                :class="theme ? [theme.surface, theme.surfaceHover, theme.text] : 'bg-white hover:bg-gray-50'"
                title="Fit to Screen">
          <i class="fas fa-expand"></i>
        </button>
      </div>
    </div>
    
    <!-- Context Menu -->
    <div v-if="showMenu" 
         :style="{ left: `${menuPosition.x}px`, top: `${menuPosition.y}px` }"
         class="absolute z-50 rounded-lg shadow-lg border py-1 min-w-48"
         :class="theme ? [theme.surface, theme.border] : 'bg-white border-gray-200'"
         @click.stop>
      <button @click="autoArrangeDefault" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
        <i class="fas fa-magic mr-3"></i>Auto-arrange
      </button>
      <button @click="autoArrangeHierarchy" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
        <i class="fas fa-sitemap mr-3"></i>Layered Layout
      </button>
      <button @click="autoArrangeTree" class="w-full px-4 py-2 text-left flex items-center transition-colors" :class="theme ? [theme.text, theme.surfaceHover] : 'hover:bg-gray-100'">
        <i class="fas fa-tree mr-3"></i>Tree Layout
      </button>
      <div class="border-t my-1" :class="theme ? theme.border : 'border-gray-200'"></div>
      <button @click="clearCanvas" class="w-full px-4 py-2 text-left flex items-center text-red-600 transition-colors" :class="theme ? theme.surfaceHover : 'hover:bg-gray-100'">
        <i class="fas fa-trash mr-3"></i>Clear Canvas
      </button>
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
    }
  },
  data() {
    return {
      selectedNode: null,
      isDragging: false,
      draggedNode: null,
      dragOffset: { x: 0, y: 0 },
      isConnecting: false,
      connectingFrom: null,
      tempConnection: { x1: 0, y1: 0, x2: 0, y2: 0 },
      zoom: 1,
      isDragOver: false,
      showMenu: false,
      menuPosition: { x: 0, y: 0 },
      nodeViewMode: 'normal' // 'compact' or 'normal'
    };
  },
  watch: {
    jobs: {
      handler(newJobs, oldJobs) {
        // Skip if oldJobs is undefined (initial load)
        if (!oldJobs) return;
        
        // Auto-arrange using tree layout when first job is added
        if (oldJobs.length === 0 && newJobs.length > 0) {
          this.$nextTick(() => {
            this.autoArrangeTree();
          });
        }
      }
    }
  },
  mounted() {
    document.addEventListener('click', this.hideContextMenu);
  },
  beforeUnmount() {
    document.removeEventListener('click', this.hideContextMenu);
  },
  methods: {
    handleDrop(event) {
      this.isDragOver = false;
      this.$emit('drop', event);
    },
    handleDragOver(event) {
      this.isDragOver = true;
      event.dataTransfer.dropEffect = 'copy';
    },
    handleDragLeave() {
      this.isDragOver = false;
    },
    selectNode(nodeId) {
      this.selectedNode = nodeId;
      this.$emit('select-job', nodeId);
    },
    startNodeDrag(event, job) {
      this.isDragging = true;
      this.draggedNode = job;
      const canvas = this.$el.querySelector('.drop-zone');
      const canvasRect = canvas.getBoundingClientRect();
      
      // Calculate the offset from the mouse position to the job's position
      this.dragOffset = {
        x: event.clientX - canvasRect.left - job.x + canvas.scrollLeft,
        y: event.clientY - canvasRect.top - job.y + canvas.scrollTop
      };
      
      // Prevent text selection while dragging
      event.preventDefault();
      
      document.addEventListener('mousemove', this.handleNodeDrag);
      document.addEventListener('mouseup', this.stopNodeDrag);
    },
    handleNodeDrag(event) {
      if (this.isDragging && this.draggedNode) {
        const canvas = this.$el.querySelector('.drop-zone');
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left - this.dragOffset.x + canvas.scrollLeft;
        const y = event.clientY - rect.top - this.dragOffset.y + canvas.scrollTop;
        
        this.draggedNode.x = Math.max(0, x);
        this.draggedNode.y = Math.max(0, y);
      }
    },
    stopNodeDrag() {
      if (this.isDragging) {
        this.isDragging = false;
        const positions = this.jobs.map(job => ({
          id: job.id,
          x: job.x,
          y: job.y
        }));
        this.$emit('update-positions', positions);
        this.draggedNode = null;
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
          const nodeWidth = this.nodeViewMode === 'compact' ? 64 : 72;
          const nodeHeight = this.nodeViewMode === 'compact' ? 36 : 44;
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
        this.tempConnection.x2 = event.clientX - rect.left + canvas.scrollLeft;
        this.tempConnection.y2 = event.clientY - rect.top + canvas.scrollTop;
      }
    },
    stopConnection(event) {
      if (this.isConnecting) {
        // Check if we're over a node's input connection point
        const element = document.elementFromPoint(event.clientX, event.clientY);
        if (element && element.parentElement) {
          const nodeElement = element.parentElement.closest('.job-node');
          if (nodeElement) {
            const toNode = this.jobs.find(j => nodeElement.textContent.includes(j.id));
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
        const nodeWidth = this.nodeViewMode === 'compact' ? 64 : 72;
        const nodeHeight = this.nodeViewMode === 'compact' ? 36 : 44;
        const x1 = fromNode.x + nodeWidth; // Center of node
        const y1 = fromNode.y + nodeHeight; // Bottom of node
        const x2 = toNode.x + nodeWidth; // Center of node
        const y2 = toNode.y; // Top of node
        
        // Create a curved path
        const dx = x2 - x1;
        const dy = y2 - y1;
        const dr = Math.sqrt(dx * dx + dy * dy);
        
        return `M ${x1} ${y1} C ${x1} ${y1 + dr * 0.3}, ${x2} ${y2 - dr * 0.3}, ${x2} ${y2}`;
      }
      return '';
    },
    getConnectionMidpoint(connection) {
      const fromNode = this.jobs.find(j => j.id === connection.from);
      const toNode = this.jobs.find(j => j.id === connection.to);
      
      if (fromNode && toNode) {
        const nodeWidth = this.nodeViewMode === 'compact' ? 64 : 72;
        const nodeHeight = this.nodeViewMode === 'compact' ? 36 : 44;
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
      this.zoom = Math.min(this.zoom + 0.1, 2);
      this.applyZoom();
    },
    zoomOut() {
      this.zoom = Math.max(this.zoom - 0.1, 0.5);
      this.applyZoom();
    },
    fitToScreen() {
      this.zoom = 1;
      this.applyZoom();
    },
    applyZoom() {
      const canvas = this.$el.querySelector('.drop-zone');
      canvas.style.transform = `scale(${this.zoom})`;
      canvas.style.transformOrigin = 'top left';
    },
    showContextMenu(event) {
      const canvas = this.$el.querySelector('.drop-zone');
      const rect = canvas.getBoundingClientRect();
      this.menuPosition = {
        x: event.clientX - rect.left + canvas.scrollLeft,
        y: event.clientY - rect.top + canvas.scrollTop
      };
      this.showMenu = true;
    },
    hideContextMenu() {
      this.showMenu = false;
    },
    autoArrangeDefault() {
      // Smart layout that combines different strategies based on workflow characteristics
      const graph = this.buildGraph();
      const analysis = this.analyzeWorkflow(graph);
      
      if (analysis.isLinear) {
        // Linear workflow - arrange in a snake pattern
        this.arrangeLinearWorkflow(graph);
      } else if (analysis.isTree) {
        // Tree structure - use tree layout
        this.autoArrangeTree();
      } else if (analysis.hasMultiplePaths) {
        // Complex DAG - use intelligent grouping
        this.arrangeComplexDAG(graph, analysis);
      } else if (analysis.hasNoConnections) {
        // No dependencies - arrange in a nice spread
        this.arrangeUnconnectedNodes();
      } else {
        // Default to layered for other cases
        this.autoArrangeHierarchy();
      }
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
      const horizontalSpacing = this.nodeViewMode === 'compact' ? 200 : 250;
      const verticalSpacing = this.nodeViewMode === 'compact' ? 100 : 120;
      const nodesPerRow = Math.floor((canvasWidth - 100) / horizontalSpacing);
      
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
      const horizontalSpacing = this.nodeViewMode === 'compact' ? 160 : 200;
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
      // Sugiyama-style layered graph layout
      const graph = this.buildGraph();
      const layers = this.assignLayers(graph);
      const orderedLayers = this.minimizeCrossings(layers, graph);
      
      // Position jobs based on optimized layers
      const verticalSpacing = this.nodeViewMode === 'compact' ? 100 : 120;
      const horizontalSpacing = this.nodeViewMode === 'compact' ? 160 : 200;
      const startY = 50;
      const canvasWidth = this.$el.querySelector('.drop-zone').offsetWidth;
      const padding = 100; // Padding from edges
      
      orderedLayers.forEach((layer, layerIndex) => {
        const totalWidth = (layer.length - 1) * horizontalSpacing;
        const availableWidth = canvasWidth - (2 * padding);
        
        // If layer fits within canvas, center it; otherwise use full width
        let startX;
        let actualSpacing = horizontalSpacing;
        
        if (totalWidth > availableWidth && layer.length > 1) {
          // Spread nodes to use full width
          actualSpacing = availableWidth / (layer.length - 1);
          startX = padding;
        } else {
          // Center the layer
          startX = (canvasWidth - totalWidth) / 2;
        }
        
        layer.forEach((jobId, index) => {
          const job = this.jobs.find(j => j.id === jobId);
          if (job) {
            job.x = startX + index * actualSpacing - (this.nodeViewMode === 'compact' ? 64 : 72);
            job.y = startY + layerIndex * verticalSpacing;
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
    assignLayers(graph) {
      const layers = [];
      const assigned = new Set();
      const level = {};
      
      // Find roots (nodes with no dependencies)
      const roots = this.jobs.filter(job => graph.inDegree[job.id] === 0);
      
      // BFS to assign layers
      const queue = roots.map(job => ({ id: job.id, layer: 0 }));
      
      while (queue.length > 0) {
        const { id, layer } = queue.shift();
        
        if (!assigned.has(id)) {
          assigned.add(id);
          level[id] = layer;
          
          if (!layers[layer]) layers[layer] = [];
          layers[layer].push(id);
          
          // Add dependent jobs to queue
          graph.edges.filter(e => e.from === id).forEach(edge => {
            if (!assigned.has(edge.to)) {
              queue.push({ id: edge.to, layer: layer + 1 });
            }
          });
        }
      }
      
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
      const nodeWidth = this.nodeViewMode === 'compact' ? 140 : 160;
      const levelHeight = this.nodeViewMode === 'compact' ? 100 : 120;
      let currentX = 50;
      
      // Layout each tree
      roots.forEach(root => {
        const treeWidth = this.layoutTree(root.id, graph, positioned, currentX, 50, nodeWidth, levelHeight);
        currentX += treeWidth + 50;
      });
      
      this.$emit('update-positions', this.jobs.map(job => ({ id: job.id, x: job.x, y: job.y })));
      this.hideContextMenu();
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
      
      // Layout children
      let childX = x;
      let totalWidth = 0;
      
      children.forEach((child, index) => {
        const childWidth = this.layoutTree(child, graph, positioned, childX, y + levelHeight, nodeWidth, levelHeight);
        childX += childWidth + 20;
        totalWidth += childWidth + (index > 0 ? 20 : 0);
      });
      
      // Center parent over children
      job.x = x + (totalWidth - nodeWidth) / 2;
      job.y = y;
      
      return totalWidth;
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
    }
  }
};
</script>

<style scoped>
.bg-grid-pattern {
  background-color: #fafafa;
  background-image: 
    linear-gradient(rgba(0, 0, 0, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.05) 1px, transparent 1px),
    linear-gradient(rgba(0, 0, 0, 0.1) 2px, transparent 2px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.1) 2px, transparent 2px);
  background-size: 20px 20px, 20px 20px, 100px 100px, 100px 100px;
  background-position: 0 0, 0 0, 0 0, 0 0;
}

.bg-grid-pattern-dark {
  background-color: transparent;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(rgba(255, 255, 255, 0.05) 2px, transparent 2px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 2px, transparent 2px);
  background-size: 20px 20px, 20px 20px, 100px 100px, 100px 100px;
  background-position: 0 0, 0 0, 0 0, 0 0;
}
</style>