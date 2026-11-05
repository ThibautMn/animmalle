import { configPath } from './lib/config.mjs'

export default defineNuxtConfig({
  compatibilityDate: '2026-11-05',
  ssr: false,
  devtools: { enabled: false },
  modules: ['@pinia/nuxt'],
  css: ['~/assets/main.css'],
  runtimeConfig: { centralConfigPath: configPath, public: { apiBase: '' } },
  app: {
    head: {
      title: 'Anim’Malle',
      htmlAttrs: { lang: 'fr' },
      meta: [
        {
          name: 'description',
          content: 'Les ressources pédagogiques du Parc national des Cévennes'
        }
      ]
    }
  }
})
