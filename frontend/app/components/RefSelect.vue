<script setup>
defineProps({ items: Array, label: String, required: Boolean })
const model = defineModel()
const id = useId()
// Astérisque de champ obligatoire affiché en rouge.
const parts = (label) => {
  const required = /\s*\*$/.test(label || '')
  return { text: (label || '').replace(/\s*\*$/, ''), required }
}
</script>
<template>
  <div>
    <label :for="id"
      >{{ parts(label).text }}<span v-if="parts(label).required" class="required-mark" aria-hidden="true"> *</span></label
    ><select :id="id" v-model="model" :required="required">
      <option :value="null">Choisir…</option>
      <option v-for="item in items" :key="item.id" :value="item.id">
        {{ item.label }}
      </option>
    </select>
  </div>
</template>
