import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'vendor-react';
          if (id.includes('/recharts/') || id.includes('/d3-')) return 'vendor-charts';
          if (id.includes('/framer-motion/')) return 'vendor-motion';
          if (id.includes('/lucide-react/')) return 'vendor-icons';
          if (id.includes('/@dnd-kit/')) return 'vendor-dnd';
          return 'vendor';
        },
      },
    },
  },
});
