import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // UI disajikan FastAPI di /ui/ (app.mount di app/main.py), satu origin dengan API
  base: '/ui/',
})
