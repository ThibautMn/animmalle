import PrimeVue from 'primevue/config'
import Button from 'primevue/button'

export default defineNuxtPlugin((app) => {
  app.vueApp.use(PrimeVue, { unstyled: true })
  app.vueApp.component('PButton', Button)
})
