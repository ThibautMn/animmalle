<script setup>
import { downloadFilename } from '../../lib/forms.mjs'
const props = defineProps({
  path: String,
  icon: String,
  filename: String,
  label: { type: String, default: 'Télécharger' }
})
const api = useApi()
const busy = ref(false)
const error = ref('')
async function download() {
  busy.value = true
  error.value = ''
  try {
    let disposition = ''
    const blob = await api(props.path, {
      responseType: 'blob',
      onResponse({ response }) {
        disposition = response.headers.get('content-disposition')
      }
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = props.filename || downloadFilename(disposition)
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <span
    ><PButton
      type="button"
      :label="icon ? undefined : label"
      :aria-label="label"
      :title="label"
      :class="{ 'icon-button': icon }"
      :disabled="busy"
      @click="download"
      ><ActionIcon v-if="icon" :name="icon" /></PButton
    ><span v-if="error" role="alert" class="error">{{ error }}</span></span
  >
</template>
