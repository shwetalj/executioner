<template>
  <div class="loading-container" :class="containerClass">
    <!-- Full overlay loading -->
    <div v-if="overlay" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 shadow-xl">
        <div class="flex flex-col items-center">
          <div class="spinner" :class="spinnerSizeClass"></div>
          <p v-if="message" class="mt-4 text-gray-700">{{ message }}</p>
        </div>
      </div>
    </div>
    
    <!-- Inline loading -->
    <div v-else class="flex items-center justify-center" :class="inline ? 'inline-flex' : ''">
      <div class="spinner" :class="spinnerSizeClass"></div>
      <p v-if="message" class="ml-3 text-gray-600">{{ message }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  size: {
    type: String,
    default: 'medium',
    validator: (value) => ['small', 'medium', 'large'].includes(value)
  },
  message: {
    type: String,
    default: ''
  },
  overlay: {
    type: Boolean,
    default: false
  },
  inline: {
    type: Boolean,
    default: false
  },
  theme: {
    type: Object,
    default: null
  }
});

const spinnerSizeClass = computed(() => {
  const sizes = {
    small: 'w-4 h-4 border-2',
    medium: 'w-8 h-8 border-3',
    large: 'w-12 h-12 border-4'
  };
  return sizes[props.size] || sizes.medium;
});

const containerClass = computed(() => {
  if (props.inline) return 'inline-block';
  if (props.overlay) return '';
  return 'flex items-center justify-center p-4';
});
</script>

<style scoped>
.spinner {
  border-radius: 50%;
  border-style: solid;
  border-color: #e5e7eb;
  border-top-color: #3b82f6;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.border-2 {
  border-width: 2px;
}

.border-3 {
  border-width: 3px;
}

.border-4 {
  border-width: 4px;
}
</style>