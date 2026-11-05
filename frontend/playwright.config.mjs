import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'

export default defineConfig({
  testDir: './tests/browser',
  timeout: 15000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:3107',
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
      args: ['--no-sandbox']
    }
  },
  webServer: {
    command: 'node .output/server/index.mjs',
    url: 'http://127.0.0.1:3107',
    env: {
      NITRO_HOST: '127.0.0.1',
      NITRO_PORT: '3107',
      NUXT_CENTRAL_CONFIG_PATH: resolve(
        '../installation/config_principal.example.yaml'
      )
    },
    reuseExistingServer: false
  }
})
