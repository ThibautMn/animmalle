<script setup>
defineProps({
  page: { type: Number, required: true },
  pageCount: { type: Number, required: true },
  entries: { type: Array, required: true },
  busy: { type: Boolean, default: false },
});
defineEmits(["go"]);
</script>
<template>
  <nav v-if="pageCount > 1" class="pagination" aria-label="Pagination">
    <PButton
      class="secondary"
      label="Précédente"
      :disabled="page === 1 || busy"
      @click="$emit('go', page - 1)"
    />
    <template v-for="(entry, index) in entries" :key="index">
      <span v-if="entry === null" class="pagination-gap">…</span>
      <PButton
        v-else
        class="secondary"
        :label="String(entry)"
        :disabled="busy"
        :aria-current="entry === page ? 'page' : undefined"
        :aria-label="`Page ${entry}`"
        @click="$emit('go', entry)"
      />
    </template>
    <PButton
      class="secondary"
      label="Suivante"
      :disabled="page >= pageCount || busy"
      @click="$emit('go', page + 1)"
    />
  </nav>
</template>
