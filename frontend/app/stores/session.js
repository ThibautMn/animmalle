import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({ user: null, is_admin: false, csrf_token: '', ready: false }),
  actions: {
    apply(data) {
      this.user = data.user
      this.is_admin = data.is_admin
      this.csrf_token = data.csrf_token
      this.ready = true
    },
    clear() {
      this.$reset()
    }
  }
})
