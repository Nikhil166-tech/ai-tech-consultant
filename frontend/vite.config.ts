import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/v1/sitemaps': 'http://localhost:8000',
      '/api/v1/refresh-runs': 'http://localhost:8000',
      '/api/v1/quarantine': 'http://localhost:8000',
      '/api/v1/health-observations': 'http://localhost:8000',
      '/api/v1/settings': 'http://localhost:8000',
      '/api/v1/auth': 'http://localhost:8000',
      '/api/v1/ask': 'http://localhost:8000',
      '/api/v1/articles': 'http://localhost:8000',
      '/api/v1/emails': 'http://localhost:3000',
      '/api/v1/inbox': 'http://localhost:3000',
      '/api/v1/autonomy': 'http://localhost:3000',
      '/api/v1/taxonomy': 'http://localhost:3000',
      '/api/v1/gmail': 'http://localhost:3000',
      '/api/v1/feedback': 'http://localhost:3000',
    }
  }
})
