<script setup>
const api = useApi()
const stats = ref(null)
const error = ref('')
const series = [
  ['y_anim_all', 'Animations'],
  ['y_anim_valid', 'Validées'],
  ['y_anim_unvalid', 'Non validées'],
  ['y_mat_peda', 'Médias'],
  ['y_outil', 'Outils']
]
const rankings = [
  ['Animations les plus consultées', 'top_animation_consultes'],
  ['Animations les plus téléchargées', 'top_animation_telecharges'],
  ['Outils facilitateurs les plus consultés', 'top_outil_consultes'],
  ['Outils facilitateurs les plus téléchargés', 'top_outil_telecharges']
]
const width = 720
const height = 220
const step = computed(() => width / Math.max(stats.value?.dates.length || 1, 1))
const labelEvery = computed(() => Math.ceil(40 / step.value))
const maxConnexions = computed(() =>
  Math.max(1, ...(stats.value?.connexions || []))
)
const barHeight = (value) => (value / maxConnexions.value) * (height - 50)
onMounted(async () => {
  try {
    stats.value = await api('/stats')
  } catch (e) {
    error.value = e.message
  }
})
</script>
<template>
  <h1>La malle en chiffres</h1>
  <p>
    Effectifs cumulés selon la dernière date de modification des ressources
    visibles.
  </p>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-else-if="!stats" role="status">Chargement…</p>
  <template v-else
    ><div class="grid">
      <div v-for="[key, label] in series" :key="key" class="card">
        <h2>{{ stats[key].at(-1) || 0 }}</h2>
        <p>{{ label }}</p>
      </div>
    </div>
    <section>
      <h2>Connexions mensuelles</h2>
      <svg
        class="chart"
        :viewBox="`0 0 ${width} ${height}`"
        role="img"
        aria-label="Connexions par mois"
      >
        <g v-for="(value, index) in stats.connexions" :key="stats.dates[index]">
          <rect
            :x="index * step + 2"
            :y="height - 30 - barHeight(value)"
            :width="Math.max(step - 4, 1)"
            :height="barHeight(value)"
            fill="currentColor"
          >
            <title>{{ stats.dates[index].slice(0, 7) }} : {{ value }}</title>
          </rect>
          <text
            v-if="index % labelEvery === 0"
            :x="index * step + step / 2"
            :y="height - 14"
            text-anchor="middle"
            font-size="10"
            fill="currentColor"
          >
            {{ stats.dates[index].slice(0, 7) }}
          </text>
        </g>
      </svg>
      <p>Maximum mensuel : {{ maxConnexions }}</p>
    </section>
    <section v-for="[title, key] in rankings" :key="key">
      <h2>{{ title }}</h2>
      <p v-if="!stats[key].length">Aucune donnée pour le moment.</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Titre</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in stats[key]" :key="item.id">
              <td>{{ item.titre }}</td>
              <td>{{ item.total }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
</template
  >
</template>
