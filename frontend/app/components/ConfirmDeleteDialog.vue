<script setup>
const { state, answer } = useConfirmDelete()
const dialog = ref(null)
watch(
  () => state.value.open,
  (open) => {
    if (open && !dialog.value?.open) dialog.value?.showModal()
    else if (!open && dialog.value?.open) dialog.value.close()
  },
)
</script>
<template>
  <dialog
    ref="dialog"
    class="confirm-dialog"
    aria-labelledby="confirm-delete-text"
    @cancel.prevent="answer(false)"
  >
    <p id="confirm-delete-text">{{ state.message }}</p>
    <div class="confirm-actions">
      <button type="button" class="confirm-cancel" @click="answer(false)">
        <ActionIcon name="back" />Annuler
      </button>
      <button type="button" class="confirm-ok" @click="answer(true)">
        <ActionIcon name="delete" />Valider
      </button>
    </div>
  </dialog>
</template>
