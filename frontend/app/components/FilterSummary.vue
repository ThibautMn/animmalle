<script setup>
// Résumé des filtres cochés : « Recherche avec a, b et SANS c, d ».
const props = defineProps({
  included: { type: Array, default: () => [] },
  excluded: { type: Array, default: () => [] }
})
const visible = computed(() => props.included.length || props.excluded.length)
</script>
<template>
  <p v-if="visible" class="filter-summary" aria-live="polite">
    Recherche
    <template v-if="included.length"><strong class="with">AVEC</strong> <strong class="with">{{ included.join(', ') }}</strong></template>
    <template v-if="included.length && excluded.length"> et </template>
    <template v-if="excluded.length"><strong class="without">SANS</strong> <strong class="without">{{ excluded.join(', ') }}</strong></template>
  </p>
</template>
