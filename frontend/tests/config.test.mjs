import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { publicSettings } from '../lib/config.mjs'

test('Seule l’origine API publique traverse la frontière serveur/client', () => {
  const directory = mkdtempSync(join(tmpdir(), 'animmalle-config-'))
  const path = join(directory, 'config.yaml')
  try {
    writeFileSync(
      path,
      'public:\n  api_url: https://api.example.org\npostgresql:\n  password: TOP_SECRET\nbackend:\n  secret_key: TOP_SECRET\n'
    )
    assert.deepEqual(publicSettings(path), {
      apiBase: 'https://api.example.org/api'
    })
    for (const value of [
      'https://user:secret@example.org',
      'file:///etc/passwd',
      'https://example.org/secret',
      'https://example.org?token=secret',
      'invalid'
    ]) {
      writeFileSync(path, `public:\n  api_url: '${value}'\n`)
      assert.throws(
        () => publicSettings(path),
        (error) => !error.message.includes('secret')
      )
    }
  } finally {
    rmSync(directory, { recursive: true })
  }
})
