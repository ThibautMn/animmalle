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
    <div class="table-wrap">
      <table>
        <caption>
          Évolution mensuelle des ressources
        </caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th v-for="[key, label] in series" :key="key" scope="col">
              {{ label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(date, index) in stats.dates" :key="date">
            <th scope="row">{{ date }}</th>
            <td v-for="[key] in series" :key="key">{{ stats[key][index] }}</td>
          </tr>
        </tbody>
      </table>
    </div></template
  >
</template>
