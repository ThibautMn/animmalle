import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { parse } from 'yaml'

export const configPath = fileURLToPath(
  new URL('../../installation/config_principal.yaml', import.meta.url)
)
export function publicSettings(path = configPath) {
  let data
  try {
    data = parse(readFileSync(path, 'utf8'))
  } catch {
    throw new Error('Configuration YAML centrale illisible')
  }
  const value = data?.public?.api_url
  let url
  try {
    url = new URL(value)
  } catch {
    throw new Error('public.api_url doit être une origine HTTP(S)')
  }
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  )
    throw new Error('public.api_url doit être une origine HTTP(S)')
  return { apiBase: `${url.origin}/api` }
}
