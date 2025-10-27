<template>
  <div class="bg-white rounded-lg shadow-md p-4 mb-4">
    <div class="flex flex-col lg:flex-row gap-4">
      <!-- Search Input -->
      <div class="flex-1">
        <div class="relative">
          <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            v-model="searchQuery"
            @input="debouncedSearch"
            type="text"
            placeholder="Search jobs by ID, description, or command..."
            class="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
          <button
            v-if="searchQuery"
            @click="clearSearch"
            class="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Filter Dropdowns -->
      <div class="flex gap-2">
        <!-- Status Filter -->
        <div class="relative">
          <button
            @click="toggleDropdown('status')"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
            <span>{{ selectedFilters.status || 'All Status' }}</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div v-if="dropdowns.status" class="absolute top-full mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
            <button
              @click="setFilter('status', null)"
              class="w-full px-4 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50 text-indigo-600': !selectedFilters.status }"
            >
              All Status
            </button>
            <button
              v-for="status in statusOptions"
              :key="status"
              @click="setFilter('status', status)"
              class="w-full px-4 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50 text-indigo-600': selectedFilters.status === status }"
            >
              {{ status }}
            </button>
          </div>
        </div>

        <!-- Dependency Filter -->
        <div class="relative">
          <button
            @click="toggleDropdown('dependencies')"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{{ getDependencyFilterLabel() }}</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <div v-if="dropdowns.dependencies" class="absolute top-full mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
            <button
              @click="setFilter('dependencies', null)"
              class="w-full px-4 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50 text-indigo-600': !selectedFilters.dependencies }"
            >
              All Jobs
            </button>
            <button
              @click="setFilter('dependencies', 'none')"
              class="w-full px-4 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50 text-indigo-600': selectedFilters.dependencies === 'none' }"
            >
              No Dependencies
            </button>
            <button
              @click="setFilter('dependencies', 'has')"
              class="w-full px-4 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50 text-indigo-600': selectedFilters.dependencies === 'has' }"
            >
              Has Dependencies
            </button>
          </div>
        </div>

        <!-- Sort Options -->
        <div class="relative">
          <button
            @click="toggleDropdown('sort')"
            class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
            </svg>
            <span>{{ getSortLabel() }}</span>
          </button>
          <div v-if="dropdowns.sort" class="absolute top-full mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
            <button
              v-for="option in sortOptions"
              :key="option.value"
              @click="setSort(option.value)"
              class="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center justify-between"
              :class="{ 'bg-indigo-50 text-indigo-600': sortBy === option.value }"
            >
              <span>{{ option.label }}</span>
              <svg v-if="sortBy === option.value" class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Active Filters Display -->
    <div v-if="hasActiveFilters" class="mt-4 flex items-center gap-2 flex-wrap">
      <span class="text-sm text-gray-600">Active filters:</span>
      <div v-if="searchQuery" class="inline-flex items-center gap-1 px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm">
        <span>Search: "{{ searchQuery }}"</span>
        <button @click="clearSearch" class="ml-1 hover:text-indigo-900">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <div v-if="selectedFilters.status" class="inline-flex items-center gap-1 px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm">
        <span>Status: {{ selectedFilters.status }}</span>
        <button @click="setFilter('status', null)" class="ml-1 hover:text-indigo-900">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <div v-if="selectedFilters.dependencies" class="inline-flex items-center gap-1 px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm">
        <span>Dependencies: {{ getDependencyFilterLabel() }}</span>
        <button @click="setFilter('dependencies', null)" class="ml-1 hover:text-indigo-900">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <button
        @click="clearAllFilters"
        class="ml-2 text-sm text-gray-500 hover:text-gray-700 underline"
      >
        Clear all
      </button>
    </div>

    <!-- Results Count -->
    <div v-if="filteredCount !== null" class="mt-4 text-sm text-gray-600">
      Showing {{ filteredCount }} of {{ totalCount }} jobs
      <span v-if="hasActiveFilters" class="text-indigo-600 font-medium">(filtered)</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useClickOutside } from '../src/composables/useEventListener.js';

const props = defineProps({
  jobs: {
    type: Array,
    default: () => []
  },
  totalCount: {
    type: Number,
    default: 0
  },
  filteredCount: {
    type: Number,
    default: null
  }
});

const emit = defineEmits(['filter-change']);

// Search and filter state
const searchQuery = ref('');
const selectedFilters = ref({
  status: null,
  dependencies: null
});
const sortBy = ref('id-asc');

// Dropdown state
const dropdowns = ref({
  status: false,
  dependencies: false,
  sort: false
});

// Filter options
const statusOptions = ['Pending', 'Running', 'Completed', 'Failed', 'Skipped'];

const sortOptions = [
  { value: 'id-asc', label: 'ID (A-Z)' },
  { value: 'id-desc', label: 'ID (Z-A)' },
  { value: 'name-asc', label: 'Name (A-Z)' },
  { value: 'name-desc', label: 'Name (Z-A)' },
  { value: 'dependencies', label: 'Dependencies' },
  { value: 'recent', label: 'Recently Modified' }
];

// Computed
const hasActiveFilters = computed(() => {
  return searchQuery.value || 
         selectedFilters.value.status || 
         selectedFilters.value.dependencies;
});

const getDependencyFilterLabel = () => {
  switch (selectedFilters.value.dependencies) {
    case 'none': return 'No Dependencies';
    case 'has': return 'Has Dependencies';
    default: return 'All Dependencies';
  }
};

const getSortLabel = () => {
  const option = sortOptions.find(o => o.value === sortBy.value);
  return option ? option.label : 'Sort';
};

// Methods
const toggleDropdown = (name) => {
  // Close all other dropdowns
  Object.keys(dropdowns.value).forEach(key => {
    if (key !== name) {
      dropdowns.value[key] = false;
    }
  });
  dropdowns.value[name] = !dropdowns.value[name];
};

const setFilter = (type, value) => {
  selectedFilters.value[type] = value;
  dropdowns.value[type] = false;
  emitFilterChange();
};

const setSort = (value) => {
  sortBy.value = value;
  dropdowns.value.sort = false;
  emitFilterChange();
};

const clearSearch = () => {
  searchQuery.value = '';
  emitFilterChange();
};

const clearAllFilters = () => {
  searchQuery.value = '';
  selectedFilters.value = {
    status: null,
    dependencies: null
  };
  sortBy.value = 'id-asc';
  emitFilterChange();
};

// Debounced search
let searchTimeout = null;
const debouncedSearch = () => {
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  searchTimeout = setTimeout(() => {
    emitFilterChange();
  }, 300);
};

const emitFilterChange = () => {
  const filters = {
    search: searchQuery.value,
    status: selectedFilters.value.status,
    dependencies: selectedFilters.value.dependencies,
    sort: sortBy.value
  };
  
  emit('filter-change', filters);
};

// Close dropdowns when clicking outside
const dropdownRef = ref(null);
useClickOutside(dropdownRef, () => {
  Object.keys(dropdowns.value).forEach(key => {
    dropdowns.value[key] = false;
  });
});

// Filter function that can be used by parent
const filterJobs = (jobs) => {
  let filtered = [...jobs];
  
  // Search filter
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(job => {
      return job.id?.toLowerCase().includes(query) ||
             job.description?.toLowerCase().includes(query) ||
             job.command?.toLowerCase().includes(query);
    });
  }
  
  // Status filter (if job status is available)
  if (selectedFilters.value.status && filtered[0]?.status) {
    filtered = filtered.filter(job => job.status === selectedFilters.value.status);
  }
  
  // Dependencies filter
  if (selectedFilters.value.dependencies) {
    if (selectedFilters.value.dependencies === 'none') {
      filtered = filtered.filter(job => !job.dependencies || job.dependencies.length === 0);
    } else if (selectedFilters.value.dependencies === 'has') {
      filtered = filtered.filter(job => job.dependencies && job.dependencies.length > 0);
    }
  }
  
  // Sort
  const [sortField, sortDirection] = sortBy.value.split('-');
  filtered.sort((a, b) => {
    let aVal, bVal;
    
    switch (sortField) {
      case 'id':
        aVal = a.id || '';
        bVal = b.id || '';
        break;
      case 'name':
        aVal = a.description || a.id || '';
        bVal = b.description || b.id || '';
        break;
      case 'dependencies':
        aVal = a.dependencies?.length || 0;
        bVal = b.dependencies?.length || 0;
        break;
      case 'recent':
        aVal = a.modifiedAt || a.createdAt || 0;
        bVal = b.modifiedAt || b.createdAt || 0;
        break;
      default:
        return 0;
    }
    
    if (sortDirection === 'desc') {
      return bVal > aVal ? 1 : bVal < aVal ? -1 : 0;
    } else {
      return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
    }
  });
  
  return filtered;
};

// Expose filter function for parent
defineExpose({
  filterJobs,
  clearAllFilters
});
</script>