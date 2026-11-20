<script setup>
// plain : sans encadré, la légende reste lue par les lecteurs d'écran.
// iconOnly : le libellé n'apparaît que si le pictogramme est absent (l'image porte alors le nom accessible).
defineProps({ items: Array, legend: String, iconOnly: Boolean, plain: Boolean })
const model = defineModel({ default: () => [] })
const excluded = defineModel('excluded', { default: undefined })
const missing = ref({})
</script>
<template>
  <fieldset :class="{ 'tag-picker-plain': plain }">
    <legend>{{ legend }}</legend>
    <div class="choices">
      <label v-for="item in items" :key="item.id"
        ><TriCheck v-model="model" v-model:excluded="excluded" :value="item.id" />
        <PictoIcon
          :id="item.id"
          :size="20"
          @missing="missing[item.id] = true"
        /><template v-if="!iconOnly || missing[item.id]">
          {{ item.label }}</template
        ></label
      >
    </div>
    <slot />
  </fieldset>
</template>
