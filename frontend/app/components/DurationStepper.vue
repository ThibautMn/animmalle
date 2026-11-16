<script setup>
// Champ de durée en minutes avec boutons − / + par paliers de 5.
// min/max : bornes de saisie ; stepFloor : plus petite valeur atteinte par les boutons.
const props = defineProps({
  id: String,
  min: { type: Number, default: 0 },
  max: { type: Number, default: 1440 },
  stepFloor: { type: Number, default: 0 },
  required: Boolean,
})
const model = defineModel({ default: null })
const current = computed(() => (Number.isInteger(model.value) ? model.value : 0))
function update(value) {
  model.value = Number.isInteger(value) ? value : null
}
// Palier de 5 minutes : s’aligne d’abord sur le multiple de 5 le plus proche.
function step(direction) {
  const next =
    direction > 0
      ? (Math.floor(current.value / 5) + 1) * 5
      : (Math.ceil(current.value / 5) - 1) * 5
  model.value = Math.min(props.max, Math.max(props.stepFloor, next))
}
</script>
<template>
  <div class="duration-stepper">
    <button
      type="button"
      aria-label="Retirer 5 minutes"
      title="Retirer 5 minutes"
      :disabled="current <= stepFloor"
      @click="step(-1)"
    >
      −
    </button>
    <input
      :id="id"
      :value="model"
      type="number"
      inputmode="numeric"
      :min="min"
      :max="max"
      step="1"
      :required="required"
      @input="update($event.target.valueAsNumber)"
      @keydown.up.prevent="step(1)"
      @keydown.down.prevent="step(-1)"
    />
    <button
      type="button"
      aria-label="Ajouter 5 minutes"
      title="Ajouter 5 minutes"
      :disabled="current >= max"
      @click="step(1)"
    >
      +
    </button>
  </div>
</template>
<style scoped>
.duration-stepper {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin-top: 5px;
  max-width: 140px;
}
.duration-stepper input {
  flex: 1;
  min-width: 0;
  margin-top: 0;
  padding-inline: 4px;
  text-align: center;
  border-radius: 0;
  appearance: textfield;
  -moz-appearance: textfield;
}
.duration-stepper input::-webkit-outer-spin-button,
.duration-stepper input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.duration-stepper button {
  flex: none;
  width: 32px;
  padding: 0;
  font-size: 1.1rem;
  line-height: 1;
  font-weight: 700;
  color: #fff;
  background: var(--c-primary);
  border: 0;
  cursor: pointer;
}
.duration-stepper button:first-child {
  border-radius: 6px 0 0 6px;
}
.duration-stepper button:last-child {
  border-radius: 0 6px 6px 0;
}
.duration-stepper button:hover:not(:disabled) {
  filter: brightness(1.12);
}
.duration-stepper button:focus-visible {
  outline: 2px solid var(--c-primary);
  outline-offset: 2px;
}
.duration-stepper button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
