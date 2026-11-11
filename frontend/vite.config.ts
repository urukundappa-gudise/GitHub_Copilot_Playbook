import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import type { Reporter, Task } from 'vitest';

function isOmitted(task: Task): boolean {
  return task.mode === 'skip' || task.mode === 'todo' ||
    task.result?.state === 'skip' || task.result?.state === 'todo' ||
    (task.type === 'suite' && task.tasks.some(isOmitted));
}

const requiredReporter: Reporter = {
  onFinished(files = []) {
    if (files.length === 0 || files.some(isOmitted)) {
      console.error('Required verification cannot omit or skip tests.');
      process.exitCode = 1;
    }
  },
};

export default defineConfig(({ mode }) => {
  const proxyTarget = loadEnv(mode, '.', 'VITE_').VITE_API_PROXY_TARGET
    ?? 'http://localhost:8000';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true, ws: true },
        '/health': { target: proxyTarget, changeOrigin: true },
      },
    },
    test: {
      reporters: process.env.VERIFY_REQUIRED === '1' ? ['default', requiredReporter] : ['default'],
      allowOnly: process.env.VERIFY_REQUIRED !== '1',
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      globals: true,
    },
  };
});
