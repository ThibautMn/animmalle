<script setup>
// Case à trois états : décochée, cochée « v » bleu (critère requis), cochée « - » rouge (critère exclu).
// Sans modèle `excluded`, elle se comporte comme une case à cocher ordinaire.
const props = defineProps({ value: { required: true } })
const included = defineModel({ default: () => [] })
const excluded = defineModel('excluded', { default: undefined })
const state = computed(() =>
  included.value.includes(props.value) ? 'include' : excluded.value?.includes(props.value) ? 'exclude' : 'none'
)
function cycle() {
  const without = (list) => list.filter((item) => item !== props.value)
  if (excluded.value === undefined) {
    included.value = state.value === 'include' ? without(included.value) : [...included.value, props.value]
  } else if (state.value === 'none') {
    included.value = [...included.value, props.value]
  } else if (state.value === 'include') {
    included.value = without(included.value)
    excluded.value = [...excluded.value, props.value]
  } else {
    excluded.value = without(excluded.value)
  }
}
const labels = { none: 'non coché', include: 'requis', exclude: 'exclu' }
</script>
<template>
  <button
    type="button"
    role="checkbox"
    :class="['tri-check', `tri-${state}`]"
    :aria-checked="state === 'none' ? 'false' : state === 'include' ? 'true' : 'mixed'"
    :title="labels[state]"
    @click.prevent.stop="cycle"
  >
    <span v-if="state === 'include'" aria-hidden="true">✓</span>
    <span v-else-if="state === 'exclude'" aria-hidden="true">−</span>
  </button>
</template>
