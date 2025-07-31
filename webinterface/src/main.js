import { createApp } from 'vue'
import App from '../App.vue'
import './style.css'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error('Global error:', err)
  console.error('Error info:', info)
}

app.mount('#app')