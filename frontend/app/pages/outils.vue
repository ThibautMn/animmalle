<script setup>
const catalog = useCatalog()
const error = ref('')
onMounted(async () => {
  try {
    await catalog.load()
  } catch (e) {
    error.value = e.message
  }
})
</script>
<template>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <div class="toolbar">
    <NuxtLink
      v-for="item in catalog
        .family('ref.type_outil')
        .filter((item) => item.code)"
      :key="item.id"
      :to="`/pages/${item.code}`"
      >{{ item.label }}</NuxtLink
    >
  </div>
  <CatalogList kind="outil" />
</template>
