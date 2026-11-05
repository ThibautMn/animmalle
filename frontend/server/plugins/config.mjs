import { defineNitroPlugin, useRuntimeConfig } from 'nitropack/runtime'
import { publicSettings } from '../../lib/config.mjs'

export default defineNitroPlugin((app) => {
  const settings = publicSettings(useRuntimeConfig().centralConfigPath)
  app.hooks.hook('request', (event) => {
    useRuntimeConfig(event).public.apiBase = settings.apiBase
  })
})
