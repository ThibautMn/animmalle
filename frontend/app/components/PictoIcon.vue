<script setup>
const emit = defineEmits(['missing'])
const props = defineProps({ id: Number, size: { type: Number, default: 28 } })
const config = useRuntimeConfig()
const catalog = useCatalog()
const missing = ref(false)
const version = useState('picto_version', () => 0)
watch(version, () => (missing.value = false))
watch(missing, (value) => value && emit('missing'))
const item = computed(() => catalog.items.value.find((i) => i.id === props.id))
const visible = computed(() => !missing.value && item.value)
</script>
<template>
  <img
    v-if="visible"
    class="picto"
    :src="`${config.public.apiBase}/thesaurus/${id}/pictogram?v=${version}`"
    :alt="item.label"
    :title="item.label"
    :width="size"
    :height="size"
    loading="lazy"
    @error="missing = true"
  />
</template>
<style scoped>
.picto {
  object-fit: contain;
  vertical-align: middle;
}
</style>
