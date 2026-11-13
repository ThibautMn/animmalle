<script setup>
// Médias d'une séquence en édition : vignettes, retrait et ajout via une fenêtre modale.
const model = defineModel({ required: true })
const props = defineProps({ media: { type: Object, required: true } })
const dialog = ref(null)
const items = computed(() => model.value.map((id) => props.media[id] || { id, nom: 'Média' }))
function add(media) {
  props.media[media.id] = media
  if (!model.value.includes(media.id)) model.value = [...model.value, media.id]
}
function remove(id) {
  model.value = model.value.filter((value) => value !== id)
}
</script>
<template>
  <div>
    <SequenceMedia :items="items" editable @remove="remove">
      <figure class="media-add">
        <button type="button" class="media-add-tile" @click="dialog.open()">
          <ActionIcon name="add" />
          <span>Ajouter un média</span>
        </button>
      </figure>
    </SequenceMedia>
    <MediaAddDialog ref="dialog" @add="add" />
  </div>
</template>
