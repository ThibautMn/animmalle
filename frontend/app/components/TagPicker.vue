<script setup>
defineProps({ items: Array, legend: String })
const model = defineModel({ default: () => [] })
</script>
<template>
  <fieldset>
    <legend>{{ legend }}</legend>
    <div class="choices">
      <label v-for="item in items" :key="item.id"
        ><input v-model="model" type="checkbox" :value="item.id" />
        <PictoIcon :id="item.id" :size="20" /> {{ item.label }}</label
      >
    </div>
  </fieldset>
</template>
