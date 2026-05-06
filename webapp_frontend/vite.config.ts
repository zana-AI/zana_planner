import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Ship pdfjs cmaps + standard fonts so non-Latin (Persian/Arabic/CJK)
    // PDFs get correct glyph→Unicode mapping for selection and rendering.
    viteStaticCopy({
      targets: [
        {
          src: 'node_modules/pdfjs-dist/cmaps/*',
          dest: 'pdfjs/cmaps',
          rename: { stripBase: 3 },
        },
        {
          src: 'node_modules/pdfjs-dist/standard_fonts/*',
          dest: 'pdfjs/standard_fonts',
          rename: { stripBase: 3 },
        },
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path, // Don't rewrite the path
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('Proxying request:', req.method, req.url);
          });
        },
      },
      '/assets': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path, // Don't rewrite the path
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
