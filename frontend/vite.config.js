import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const viteEnvironment = loadEnv(mode, '.', 'VITE_');
    const proxyTarget = process.env.VITE_API_PROXY_TARGET
        ?? viteEnvironment.VITE_API_PROXY_TARGET
        ?? 'http://localhost:8000';
    const frontendPort = Number(
        process.env.VITE_DEV_PORT ?? viteEnvironment.VITE_DEV_PORT ?? 5173,
    );

    return {
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: frontendPort,
        proxy: {
            '/api': { target: proxyTarget, changeOrigin: true, ws: true },
            '/health': { target: proxyTarget, changeOrigin: true },
        },
    },
    test: {
        environment: 'jsdom',
        setupFiles: './src/test/setup.ts',
        globals: true,
    },
    };
});
