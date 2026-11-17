<script setup>
defineProps({ fields: Array })
const model = defineModel({ required: true })
</script>
<template>
  <div v-for="[key, label] in fields" :key="key" class="rich-field"
    ><span class="rich-label">{{ label }}</span><RichEditor v-model="model[key]" :label="label" />
  </div>
</template>
