/**
 * Node positioning utilities for preventing overlaps and managing layouts
 */

/**
 * Detect if two nodes overlap
 */
export function nodesOverlap(node1, node2, minDistance = 50) {
  const dx = Math.abs(node1.x - node2.x);
  const dy = Math.abs(node1.y - node2.y);
  
  // Consider nodes overlapping if they're closer than minDistance
  return dx < minDistance && dy < minDistance;
}

/**
 * Detect all overlapping nodes in a collection
 */
export function detectOverlaps(nodes, minDistance = 50) {
  const overlaps = [];
  
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      if (nodesOverlap(nodes[i], nodes[j], minDistance)) {
        overlaps.push([nodes[i], nodes[j]]);
      }
    }
  }
  
  return overlaps;
}

/**
 * Fix overlapping nodes using a force-directed approach
 */
export function fixOverlappingNodes(nodes, options = {}) {
  const {
    minDistance = 120,      // Minimum distance between nodes
    maxIterations = 50,     // Maximum iterations to prevent infinite loops
    nodeWidth = 180,        // Width of node box
    nodeHeight = 80,        // Height of node box
    padding = 20            // Additional padding around nodes
  } = options;
  
  const fixedNodes = nodes.map(node => ({ ...node }));
  const actualMinDistance = Math.max(nodeWidth, nodeHeight) + padding;
  
  let iterations = 0;
  let hasOverlaps = true;
  
  while (hasOverlaps && iterations < maxIterations) {
    hasOverlaps = false;
    
    // Check each pair of nodes
    for (let i = 0; i < fixedNodes.length; i++) {
      for (let j = i + 1; j < fixedNodes.length; j++) {
        const node1 = fixedNodes[i];
        const node2 = fixedNodes[j];
        
        const dx = node2.x - node1.x;
        const dy = node2.y - node1.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        // If nodes are too close or at exact same position
        if (distance < actualMinDistance || (dx === 0 && dy === 0)) {
          hasOverlaps = true;
          
          // Calculate repulsion force
          let forceX, forceY;
          
          if (distance === 0) {
            // Nodes at exact same position - push in random direction
            const angle = Math.random() * Math.PI * 2;
            forceX = Math.cos(angle) * actualMinDistance;
            forceY = Math.sin(angle) * actualMinDistance;
          } else {
            // Push nodes apart proportionally
            const force = (actualMinDistance - distance) / 2;
            forceX = (dx / distance) * force;
            forceY = (dy / distance) * force;
          }
          
          // Apply force to both nodes
          node1.x -= forceX;
          node1.y -= forceY;
          node2.x += forceX;
          node2.y += forceY;
        }
      }
    }
    
    iterations++;
  }
  
  // Ensure no negative positions
  const minX = Math.min(...fixedNodes.map(n => n.x));
  const minY = Math.min(...fixedNodes.map(n => n.y));
  
  if (minX < 100 || minY < 100) {
    const offsetX = minX < 100 ? 100 - minX : 0;
    const offsetY = minY < 100 ? 100 - minY : 0;
    
    fixedNodes.forEach(node => {
      node.x += offsetX;
      node.y += offsetY;
    });
  }
  
  return fixedNodes;
}

/**
 * Smart auto-arrange that preserves manual arrangements when possible
 */
export function smartAutoArrange(nodes, dependencies = [], options = {}) {
  const {
    preserveManual = true,   // Try to preserve manually positioned nodes
    horizontalSpacing = 200,
    verticalSpacing = 120,
    startX = 100,
    startY = 100
  } = options;
  
  // First, identify nodes that have been manually positioned
  // (not at origin and not in a perfect grid)
  const manuallyPositioned = new Set();
  
  if (preserveManual) {
    nodes.forEach(node => {
      // Consider a node manually positioned if it's not at origin
      // and not at a common auto-arrange position
      if (node.x !== 0 && node.y !== 0 && 
          node.x !== undefined && node.y !== undefined) {
        manuallyPositioned.add(node.id);
      }
    });
  }
  
  // Build dependency graph
  const graph = new Map();
  const inDegree = new Map();
  
  nodes.forEach(node => {
    graph.set(node.id, []);
    inDegree.set(node.id, 0);
  });
  
  dependencies.forEach(dep => {
    if (graph.has(dep.from) && graph.has(dep.to)) {
      graph.get(dep.from).push(dep.to);
      inDegree.set(dep.to, (inDegree.get(dep.to) || 0) + 1);
    }
  });
  
  // Topological sort to determine layers
  const layers = [];
  const queue = [];
  const visited = new Set();
  
  // Start with nodes that have no dependencies
  inDegree.forEach((degree, nodeId) => {
    if (degree === 0) {
      queue.push(nodeId);
    }
  });
  
  while (queue.length > 0) {
    const currentLayer = [...queue];
    layers.push(currentLayer);
    queue.length = 0;
    
    currentLayer.forEach(nodeId => {
      visited.add(nodeId);
      const children = graph.get(nodeId) || [];
      
      children.forEach(childId => {
        const childDegree = inDegree.get(childId) - 1;
        inDegree.set(childId, childDegree);
        
        if (childDegree === 0 && !visited.has(childId)) {
          queue.push(childId);
        }
      });
    });
  }
  
  // Position nodes by layers
  const positionedNodes = nodes.map(node => {
    const newNode = { ...node };
    
    // If manually positioned and we want to preserve, keep position
    if (manuallyPositioned.has(node.id) && preserveManual) {
      return newNode;
    }
    
    // Find which layer this node belongs to
    let layerIndex = -1;
    let positionInLayer = -1;
    
    for (let i = 0; i < layers.length; i++) {
      const index = layers[i].indexOf(node.id);
      if (index !== -1) {
        layerIndex = i;
        positionInLayer = index;
        break;
      }
    }
    
    // If not in any layer (disconnected node), add to last layer
    if (layerIndex === -1) {
      layerIndex = layers.length;
      positionInLayer = 0;
    }
    
    // Calculate position
    newNode.x = startX + (layerIndex * horizontalSpacing);
    newNode.y = startY + (positionInLayer * verticalSpacing);
    
    return newNode;
  });
  
  // Fix any remaining overlaps
  return fixOverlappingNodes(positionedNodes, {
    minDistance: Math.min(horizontalSpacing, verticalSpacing),
    nodeWidth: 180,
    nodeHeight: 80
  });
}

/**
 * Check if nodes need repositioning
 */
export function needsRepositioning(nodes) {
  // Check if all nodes are at origin
  const allAtOrigin = nodes.every(node => 
    node.x === 0 && node.y === 0
  );
  
  if (allAtOrigin) return true;
  
  // Check for significant overlaps
  const overlaps = detectOverlaps(nodes, 50);
  
  // If more than 30% of nodes are overlapping, needs repositioning
  const overlapThreshold = Math.floor(nodes.length * 0.3);
  return overlaps.length > overlapThreshold;
}

/**
 * Distribute nodes evenly in available space
 */
export function distributeNodes(nodes, options = {}) {
  const {
    canvasWidth = 1200,
    canvasHeight = 800,
    margin = 100,
    nodeWidth = 180,
    nodeHeight = 80
  } = options;
  
  const availableWidth = canvasWidth - (2 * margin);
  const availableHeight = canvasHeight - (2 * margin);
  
  // Calculate grid dimensions
  const nodeCount = nodes.length;
  const cols = Math.ceil(Math.sqrt(nodeCount * (availableWidth / availableHeight)));
  const rows = Math.ceil(nodeCount / cols);
  
  const spacingX = availableWidth / (cols - 1 || 1);
  const spacingY = availableHeight / (rows - 1 || 1);
  
  return nodes.map((node, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    
    return {
      ...node,
      x: margin + (col * spacingX),
      y: margin + (row * spacingY)
    };
  });
}