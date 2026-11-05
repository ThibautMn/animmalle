<script setup>
defineProps({ items: Array, label: String, required: Boolean })
const model = defineModel()
const id = useId()
</script>
<template>
  <div>
    <label :for="id">{{ label }}</label
    ><select :id="id" v-model="model" :required="required">
      <option :value="null">Choisir…</option>
      <option v-for="item in items" :key="item.id" :value="item.id">
        {{ item.label }}
      </option>
    </select>
  </div>
</template>
