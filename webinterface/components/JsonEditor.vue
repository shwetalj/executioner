<template>
  <div class="h-full flex flex-col bg-gray-900">
    <!-- Editor Header -->
    <div class="flex items-center justify-between px-4 py-2 border-b bg-black border-gray-700">
      <div class="flex items-center space-x-2">
        <span class="text-sm text-gray-400 font-mono">JSON Configuration</span>
        <span v-if="!isValid" class="text-xs text-red-400 font-mono">
          <i class="fas fa-times-circle mr-1"></i>[ERROR]
        </span>
        <span v-else class="text-xs text-blue-400 font-mono">
          <i class="fas fa-check-circle mr-1"></i>[OK]
        </span>
      </div>
      <div class="flex items-center space-x-2">
        <button @click="toggleLineNumbers" 
                class="px-3 py-1 text-sm rounded transition-colors font-mono"
                :class="showLineNumbers ? 'bg-blue-600 hover:bg-blue-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700'">
          <i class="fas fa-list-ol mr-1"></i>Lines
        </button>
        <button @click="formatJson" :disabled="!isValid"
                class="px-3 py-1 text-sm rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-mono bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700">
          <i class="fas fa-magic mr-1"></i>Format
        </button>
        <button @click="copyJson" 
                class="px-3 py-1 text-sm rounded transition-colors font-mono bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700">
          <i class="fas fa-copy mr-1"></i>Copy
        </button>
      </div>
    </div>
    
    <!-- JSON Editor -->
    <div class="flex-1 relative overflow-hidden">
      <textarea
        ref="editor"
        v-model="localJson"
        @input="validateAndUpdate"
        class="absolute inset-0 w-full h-full p-4 font-mono text-base resize-none focus:outline-none bg-gray-900"
        :class="[isValid ? 'text-gray-300' : 'text-red-400', { 'pl-16': showLineNumbers }]"
        spellcheck="false"
        placeholder="Enter JSON configuration..."
        style="background-color: #0d1117;"
      ></textarea>
      
      <!-- Line numbers -->
      <div v-if="showLineNumbers" class="absolute left-0 top-0 bottom-0 w-14 border-r overflow-hidden pointer-events-none bg-black border-gray-700">
        <div class="p-4 text-right" :style="{ transform: `translateY(-${scrollOffset}px)` }">
          <div v-for="line in lineCount" :key="line" class="text-base font-mono leading-6 text-gray-500">
            {{ line }}
          </div>
        </div>
      </div>
    </div>
    
    <!-- Error Display -->
    <div v-if="errorMessage" class="px-4 py-2 text-sm bg-red-900 text-red-400 font-mono border-t border-red-800">
      <i class="fas fa-exclamation-triangle mr-2"></i>{{ errorMessage }}
    </div>
  </div>
</template>

<script>
export default {
  name: 'JsonEditor',
  props: {
    modelValue: {
      type: String,
      required: true
    },
    theme: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      localJson: this.modelValue,
      isValid: true,
      errorMessage: '',
      showLineNumbers: false,
      scrollOffset: 0
    };
  },
  computed: {
    lineCount() {
      return this.localJson.split('\n').length;
    }
  },
  watch: {
    modelValue(newVal) {
      if (newVal !== this.localJson) {
        this.localJson = newVal;
        this.validateJson();
      }
    }
  },
  mounted() {
    this.validateJson();
    
    // Sync line numbers scroll with textarea
    if (this.$refs.editor) {
      this.$refs.editor.addEventListener('scroll', this.handleScroll);
    }
  },
  beforeUnmount() {
    if (this.$refs.editor) {
      this.$refs.editor.removeEventListener('scroll', this.handleScroll);
    }
  },
  methods: {
    handleScroll(event) {
      this.scrollOffset = event.target.scrollTop;
    },
    toggleLineNumbers() {
      this.showLineNumbers = !this.showLineNumbers;
      // Save preference
      localStorage.setItem('jsonEditorLineNumbers', this.showLineNumbers);
    },
    validateAndUpdate() {
      this.validateJson();
      if (this.isValid) {
        this.$emit('update', this.localJson);
      }
    },
    validateJson() {
      try {
        JSON.parse(this.localJson);
        this.isValid = true;
        this.errorMessage = '';
      } catch (error) {
        this.isValid = false;
        this.errorMessage = error.message;
      }
    },
    formatJson() {
      if (this.isValid) {
        try {
          const parsed = JSON.parse(this.localJson);
          this.localJson = JSON.stringify(parsed, null, 2);
          this.$emit('update', this.localJson);
        } catch (error) {
          console.error('Format error:', error);
        }
      }
    },
    copyJson() {
      navigator.clipboard.writeText(this.localJson).then(() => {
        // Show temporary success message
        const originalText = this.errorMessage;
        this.errorMessage = 'Copied to clipboard!';
        setTimeout(() => {
          this.errorMessage = originalText;
        }, 2000);
      });
    }
  },
  created() {
    // Load saved preferences
    const savedLineNumbers = localStorage.getItem('jsonEditorLineNumbers');
    if (savedLineNumbers !== null) {
      this.showLineNumbers = savedLineNumbers === 'true';
    }
  }
};
</script>

<style scoped>
textarea {
  tab-size: 2;
  line-height: 1.5rem;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  letter-spacing: 0.5px;
}

textarea::-webkit-scrollbar {
  width: 10px;
  background-color: #0d1117;
}

textarea::-webkit-scrollbar-track {
  background-color: #0d1117;
}

textarea::-webkit-scrollbar-thumb {
  background-color: #30363d;
  border-radius: 5px;
}

textarea::-webkit-scrollbar-thumb:hover {
  background-color: #484f58;
}

/* Terminal-style cursor */
textarea {
  caret-color: #58a6ff;
  caret-shape: block;
}

/* Selection color */
textarea::selection {
  background-color: #3a3d41;
  color: #ffffff;
}

/* Placeholder text */
textarea::placeholder {
  color: #484f58;
  font-style: italic;
}
</style>