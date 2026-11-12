<script setup>
const props = defineProps({ items: { type: Array, required: true } })
const api = useApi()
const catalog = useCatalog()
const sources = ref({})
const errors = ref({})
let disposed = false
const items = computed(() => props.items.filter(Boolean))
function kind(item) {
  const label = catalog.label(item.fk_type_mat_id).toLocaleLowerCase()
  if (/image|photo/.test(label)) return 'image'
  if (/son|audio|musique/.test(label)) return 'audio'
  return 'other'
}
const images = computed(() => items.value.filter(item => kind(item) === 'image'))
const sounds = computed(() => items.value.filter(item => kind(item) === 'audio'))
const others = computed(() => items.value.filter(item => kind(item) === 'other'))
onMounted(async () => {
  await Promise.all(items.value.filter(item => kind(item) !== 'other').map(async item => {
    try {
      const blob = await api(`/materials/${item.id}/preview`, { responseType: 'blob' })
      if (disposed) return
      if (!blob.type.startsWith(`${kind(item)}/`)) throw new Error('Format de fichier incompatible avec ce type de média.')
      sources.value[item.id] = URL.createObjectURL(blob)
    } catch (error) {
      if (!disposed) errors.value[item.id] = error.message
    }
  }))
})
onBeforeUnmount(() => {
  disposed = true
  Object.values(sources.value).forEach(source => URL.revokeObjectURL(source))
})
</script>
<template>
  <div v-if="images.length" class="sequence-images">
    <figure v-for="item in images" :key="item.id">
      <MediaPreview v-if="sources[item.id]" :id="item.id" icon class="thumbnail-preview">
        <img :src="sources[item.id]" :alt="item.nom" />
      </MediaPreview>
      <p v-else-if="errors[item.id]" role="alert">{{ errors[item.id] }}</p>
      <p v-else role="status">Chargement…</p>
      <figcaption>
        <NuxtLink :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
        <DownloadButton
          :path="`/materials/${item.id}/file`"
          icon="download"
          :label="`Télécharger ${item.nom}`"
        />
      </figcaption>
    </figure>
  </div>
  <div v-if="sounds.length" class="sequence-sounds">
    <div v-for="item in sounds" :key="item.id" class="sequence-sound">
      <audio v-if="sources[item.id]" :src="sources[item.id]" controls preload="metadata" :aria-label="item.nom" />
      <p v-else-if="errors[item.id]" role="alert">{{ errors[item.id] }}</p>
      <p v-else role="status">Chargement…</p>
      <NuxtLink :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
      <DownloadButton
        :path="`/materials/${item.id}/file`"
        icon="download"
        :label="`Télécharger ${item.nom}`"
      />
    </div>
  </div>
  <ul v-if="others.length" class="sequence-media">
    <li v-for="item in others" :key="item.id">
      <NuxtLink :to="`/materials/${item.id}`">{{ item.nom }}</NuxtLink>
      <MediaPreview :id="item.id" icon />
    </li>
  </ul>
</template>
