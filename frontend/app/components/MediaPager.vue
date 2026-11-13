<script setup>
defineProps({
  page: { type: Number, required: true },
  pageCount: { type: Number, required: true },
  busy: Boolean
})
defineEmits(['go'])
</script>
<template>
  <nav v-if="pageCount > 1" class="media-pager" aria-label="Pagination">
    <PButton
      type="button"
      class="icon-button secondary"
      aria-label="Page précédente"
      title="Page précédente"
      :disabled="page === 1 || busy"
      @click="$emit('go', page - 1)"
      ><ActionIcon name="prev"
    /></PButton>
    <span>Page {{ page }} / {{ pageCount }}</span>
    <PButton
      type="button"
      class="icon-button secondary"
      aria-label="Page suivante"
      title="Page suivante"
      :disabled="page >= pageCount || busy"
      @click="$emit('go', page + 1)"
      ><ActionIcon name="next"
    /></PButton>
  </nav>
</template>
