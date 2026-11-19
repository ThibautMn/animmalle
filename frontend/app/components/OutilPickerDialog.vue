<script setup>
// Fenêtre modale listant les outils facilitateurs (mêmes recherche et filtres que la page des outils)
// pour en ajouter un à l'animation en cours d'édition.
defineProps({ selected: { type: Array, default: () => [] } })
const emit = defineEmits(['add'])
const dialog = ref(null)
// Liste montée seulement à l'ouverture : pas de recherche inutile tant que la fenêtre est fermée.
const opened = ref(false)
function open() {
  opened.value = true
  dialog.value.showModal()
}
function close() {
  dialog.value?.close()
}
defineExpose({ open, close })
</script>
<template>
  <dialog
    ref="dialog"
    class="media-add-dialog outil-picker-dialog"
    aria-label="Ajouter un outil facilitateur"
    @close="opened = false"
    @click="$event.target === dialog && close()"
  >
    <div class="toolbar">
      <h2>Ajouter un outil facilitateur</h2>
      <PButton
        type="button"
        class="icon-button secondary dialog-close"
        aria-label="Fermer"
        title="Fermer"
        @click="close"
        ><ActionIcon name="close"
      /></PButton>
    </div>
    <CatalogList
      v-if="opened"
      kind="outil"
      picker
      :selected="selected"
      @pick="(outil) => emit('add', outil)"
    />
  </dialog>
</template>
<style>
.outil-picker-dialog {
  width: min(1200px, 96vw);
  height: 90vh;
  overflow-y: auto;
}
</style>
