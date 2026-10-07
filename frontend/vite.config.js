import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  build: {
    // Keep the shopper's download small: the heavy admin-only libraries (the rich-text editor,
    // charts) go into their own files, fetched only when the admin area is opened.
    // The rich-text editor is one big library (about 1.2 MB) and cannot usefully be split
    // further. It is only ever fetched when the owner opens Add or Edit Product, so the limit
    // is set above it rather than leaving a warning that means nothing.
    chunkSizeWarningLimit: 1300,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('ckeditor')) return 'editor';
          if (id.includes('chart.js') || id.includes('react-chartjs')) return 'charts';
          if (id.includes('sweetalert2')) return 'dialogs';
          if (id.includes('moment')) return 'dates';
          return undefined;
        },
      },
    },
  },
  plugins: [react()],
})