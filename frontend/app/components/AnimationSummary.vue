<script setup>
import { formatMinutes } from '../../lib/forms.mjs'
const props = defineProps({ item: { type: Object, required: true } })
const catalog = useCatalog()
const groups = computed(() =>
  ['ref.thematiques', 'ref.saison', 'ref.public', 'ref.lieux']
    .map((code) => ({
      code,
      label: catalog.items.value.find((tag) => tag.code === code)?.label || '',
      tags: props.item.tags.filter(
        (id) =>
          catalog.items.value.find((tag) => tag.id === id)?.reference === code,
      ),
    }))
    .filter((group) => group.tags.length),
)
const sequencesLabel = computed(() => {
  const total = props.item.sequences.reduce(
    (sum, seq) =>
      sum + (Number.isInteger(seq.duree_minutes) ? seq.duree_minutes : 0),
    0,
  )
  const count = String(props.item.sequences.length)
  const duration = formatMinutes(total)
  return duration ? `${count} (${duration})` : count
})
const facts = computed(() =>
  [
    ['Durée', catalog.label(props.item.fk_duree_id)],
    ['Lieu', props.item.lieu],
    ['Séquences', sequencesLabel.value],
  ].filter(([, value]) => value),
)
</script>
<template>
  <section class="summary card" aria-label="Informations clés">
    <dl class="facts">
      <div v-for="[label, value] in facts" :key="label">
        <dt>{{ label }}</dt>
        <dd>{{ value }}</dd>
      </div>
    </dl>
    <div v-for="group in groups" :key="group.code" class="tag-group">
      <h2>{{ group.label }}</h2>
      <ul>
        <li v-for="id in group.tags" :key="id">
          <PictoIcon :id="id" :size="32" /><span>{{ catalog.label(id) }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>
<style scoped>
.summary {
  display: grid;
  gap: 16px;
}
.facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 32px;
  margin: 0;
}
.facts dt {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-muted);
}
.facts dd {
  margin: 0;
  font-weight: 600;
}
.tag-group h2 {
  margin: 0 0 6px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-muted);
}
.tag-group ul {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tag-group li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 4px;
  border-radius: 20px;
  background: var(--c-primary-soft);
  font-size: 0.9rem;
}
</style>
