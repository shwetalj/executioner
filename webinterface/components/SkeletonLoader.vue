<template>
  <div class="skeleton-loader">
    <!-- Job List Skeleton -->
    <div v-if="type === 'job-list'" class="space-y-2">
      <div v-for="i in count" :key="i" class="skeleton-job">
        <div class="flex items-center p-3 rounded-lg" :class="theme ? theme.surface : 'bg-gray-100'">
          <div class="skeleton-circle w-8 h-8 mr-3"></div>
          <div class="flex-1 space-y-2">
            <div class="skeleton-line h-4 w-3/4"></div>
            <div class="skeleton-line h-3 w-1/2"></div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Canvas Skeleton -->
    <div v-else-if="type === 'canvas'" class="relative w-full h-full">
      <div class="absolute inset-0 flex items-center justify-center">
        <div class="text-gray-400">
          <svg class="w-16 h-16 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 3.5a1.5 1.5 0 013 0V4a1 1 0 001 1h3.5a1.5 1.5 0 010 3H14a1 1 0 00-1 1v3.5a1.5 1.5 0 01-3 0V9a1 1 0 00-1-1H5.5a1.5 1.5 0 010-3H9a1 1 0 001-1v-.5z" />
          </svg>
          <p class="mt-2 text-sm">Loading workflow...</p>
        </div>
      </div>
    </div>
    
    <!-- Config Skeleton -->
    <div v-else-if="type === 'config'" class="space-y-4 p-4">
      <div v-for="i in 5" :key="i" class="space-y-2">
        <div class="skeleton-line h-4 w-1/4"></div>
        <div class="skeleton-line h-10 w-full rounded"></div>
      </div>
    </div>
    
    <!-- Generic Lines Skeleton -->
    <div v-else class="space-y-3">
      <div v-for="i in count" :key="i" class="skeleton-line" 
           :style="{ width: getRandomWidth() }"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  type: {
    type: String,
    default: 'lines',
    validator: (value) => ['lines', 'job-list', 'canvas', 'config'].includes(value)
  },
  count: {
    type: Number,
    default: 3
  },
  theme: {
    type: Object,
    default: null
  }
});

const getRandomWidth = () => {
  const widths = ['75%', '100%', '60%', '90%', '80%'];
  return widths[Math.floor(Math.random() * widths.length)];
};
</script>

<style scoped>
.skeleton-line {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  height: 1rem;
  border-radius: 0.25rem;
}

.skeleton-circle {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: 50%;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Dark theme support */
.dark .skeleton-line,
.dark .skeleton-circle {
  background: linear-gradient(
    90deg,
    #374151 25%,
    #4b5563 50%,
    #374151 75%
  );
  background-size: 200% 100%;
}
</style>