<script setup>
defineProps({ fields: Array })
const model = defineModel({ required: true })
</script>
<template>
  <label v-for="[key, label] in fields" :key="key"
    >{{ label }}<textarea v-model="model[key]" maxlength="100000" />
  </label>
</template>
