<script setup>
defineProps({ sequences: { type: Array, required: true } })
const catalog = useCatalog()
</script>
<template>
  <nav
    v-if="sequences.length"
    class="toc card"
    aria-label="Sommaire des séquences"
  >
    <h2>Déroulé</h2>
    <ol>
      <li v-for="(seq, index) in sequences" :key="seq.id">
        <a :href="`#seq-${index + 1}`"
          ><span class="toc-title">{{ seq.titre }}</span
          ><span v-if="catalog.label(seq.fk_duree_id)" class="toc-duration">{{
            catalog.label(seq.fk_duree_id)
          }}</span></a
        >
      </li>
    </ol>
  </nav>
</template>
<style scoped>
.toc h2 {
  margin: 0 0 8px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-muted);
}
.toc ol {
  margin: 0;
  padding-left: 1.4em;
}
.toc li {
  padding: 3px 0;
}
.toc a {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  text-decoration: none;
  color: var(--c-text);
}
.toc a:hover .toc-title {
  color: var(--c-primary-dark);
  text-decoration: underline;
}
.toc-duration {
  color: var(--c-muted);
  font-size: 0.85rem;
}
@media (max-width: 900px) {
  .toc ol {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 0;
    list-style: none;
  }
  .toc li {
    padding: 0;
  }
  .toc a {
    padding: 2px 12px;
    border-radius: 20px;
    background: var(--c-primary-soft);
  }
}
</style>
