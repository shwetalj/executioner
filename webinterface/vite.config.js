import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/executioner/',
  plugins: [vue()],
  server: {
    port: 5173,
    open: true
  }
})