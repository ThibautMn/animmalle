<script setup>
// Tuile d'un média : vignette réelle si disponible, sinon icône du format.
defineProps({
  item: { type: Object, required: true },
  kind: { type: String, required: true },
  source: { type: String, default: '' },
  image: Boolean,
  extension: { type: String, default: '' }
})
</script>
<template>
  <span v-if="image" :class="['video-thumbnail', `thumbnail-${kind}`]">
    <img :src="source" :alt="item.nom" />
    <span v-if="kind === 'video'" class="play-badge" aria-hidden="true" />
    <span v-else-if="kind === 'pdf'" class="media-badge pdf-badge" aria-hidden="true">
      <FileTypeIcon kind="pdf" :size="14" />PDF
    </span>
    <span v-else-if="['presentation', 'document'].includes(kind)" :class="['media-badge', `${kind}-badge`]" aria-hidden="true">
      <FileTypeIcon :kind="kind" :size="14" />{{ extension }}
    </span>
    <span v-else-if="kind === 'image'" class="media-badge image-badge" aria-hidden="true">
      <FileTypeIcon kind="image" :size="14" />
    </span>
  </span>
  <span v-else :class="['file-tile', `file-tile--${kind}`]">
    <FileTypeIcon v-if="kind !== 'video'" :kind="kind" />
    <span v-else class="play-badge" aria-hidden="true" />
    <span v-if="extension" class="file-ext">{{ extension }}</span>
  </span>
</template>
