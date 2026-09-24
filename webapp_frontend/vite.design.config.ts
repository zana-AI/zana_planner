// Opt-in UI sandbox. This config is never used by the production build.
import { defineConfig, mergeConfig } from 'vite';
import base from './vite.config';

export default mergeConfig(base, defineConfig({
  plugins: [{
    name: 'isolated-design-preview',
    transformIndexHtml() {
      return [{ tag: 'script', attrs: { src: '/api/__preview/controls.js' }, injectTo: 'head-prepend' }];
    },
  }],
  server: {
    host: '127.0.0.1', port: 5174, strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8088' },
      '/assets': { target: 'http://127.0.0.1:8088' },
      '/youtube-watch': { target: 'http://127.0.0.1:8088' },
    },
  },
}));
