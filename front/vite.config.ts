import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/GymApp/', // GitHub Pages путь (если репозиторий не в корне)
})