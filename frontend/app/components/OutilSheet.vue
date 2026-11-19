<script setup>
// Fiche complète d'un outil facilitateur (lecture seule), partagée par la page de l'outil
// et par la fiche d'une animation.
import { toPlainText } from '../../lib/richtext.mjs'
import { outilFields } from '../../lib/forms.mjs'
defineProps({
  item: { type: Object, required: true },
  // Titre de niveau 3 plutôt que 1 quand la fiche est incluse dans une autre page.
  embedded: Boolean
})
const catalog = useCatalog()
const fields = outilFields.filter(([key]) => key !== 'materiel')
</script>
<template>
  <div class="tool-sheet tools-tint">
    <header class="toolbar tool-header">
      <div class="tool-title">
        <small v-if="embedded" class="tool-kicker">Outil facilitateur</small>
        <component :is="embedded ? 'h3' : 'h1'">{{ item.nom }}</component>
        <small class="muted">Modifiée le {{ item.date_modif || '—' }}</small>
      </div>
      <span class="tool-badges">
        <span class="badge">{{ catalog.label(item.fk_type_outil_id) }}</span>
        <span v-if="catalog.label(item.difficulte_id)" class="badge">{{
          catalog.label(item.difficulte_id)
        }}</span>
      </span>
    </header>
    <div
      :class="[
        'tool-body',
        !item.has_file && !toPlainText(item.materiel) && 'tool-body-single'
      ]"
    >
      <div class="tool-main">
        <fieldset
          v-for="[key, label] in fields.filter(
            ([key]) => key !== 'variante' || item[key]
          )"
          :key="key"
          :class="['tool-block', key === 'variante' && 'tool-block-variante']"
        >
          <legend>{{ label }}</legend>
          <RichText v-if="item[key]" :text="item[key]" />
          <p v-else class="prose">Non renseigné</p>
        </fieldset>
      </div>
      <aside v-if="item.has_file || toPlainText(item.materiel)" class="tool-side">
        <SequenceMedia
          v-if="item.has_file"
          :items="[item]"
          base="/outils"
          bare
          class="tool-thumb"
        />
        <fieldset
          v-if="toPlainText(item.materiel)"
          class="tool-block tool-block-materiel"
        >
          <legend>Matériel</legend>
          <RichText :text="item.materiel" />
        </fieldset>
      </aside>
    </div>
  </div>
</template>
