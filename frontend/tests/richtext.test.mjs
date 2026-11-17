import { test } from 'node:test'
import assert from 'node:assert/strict'
import { toRichHtml, toPlainText } from '../lib/richtext.mjs'

test('texte brut converti en HTML échappé', () => {
  assert.equal(toRichHtml('a <x>\nc\n\nd'), '<p>a &lt;x&gt;<br>c</p><p>d</p>')
  assert.equal(toRichHtml(''), '')
})
test('HTML conservé et converti en texte brut', () => {
  assert.equal(toRichHtml('<p>x</p>'), '<p>x</p>')
  assert.equal(toPlainText('<p>a &amp; b</p><p>c</p>'), 'a & b\nc')
})
