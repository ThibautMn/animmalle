import { ofetch } from 'ofetch'
import { useSessionStore } from '~/stores/session'

export function useApi() {
  const session = useSessionStore()
  const config = useRuntimeConfig()
  return async (path, options = {}) => {
    try {
      return await ofetch(path, {
        baseURL: config.public.apiBase,
        credentials: 'include',
        retry: 0,
        ...options,
        headers: {
          ...(session.csrf_token ? { 'X-CSRF-Token': session.csrf_token } : {}),
          ...options.headers
        }
      })
    } catch (error) {
      if (error.status === 401 && path !== '/auth/login') session.clear()
      let data = error.data
      if (typeof Blob !== 'undefined' && data instanceof Blob) {
        try {
          data = JSON.parse(await data.text())
        } catch {
          data = null
        }
      }
      const detail = data?.error
      throw Object.assign(
        new Error(
          detail
            ? `${detail.message}${detail.fields ? ' — ' + JSON.stringify(detail.fields) : ''}`
            : 'Le service est inaccessible. Réessayez.'
        ),
        { status: error.status }
      )
    }
  }
}
