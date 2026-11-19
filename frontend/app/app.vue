<script setup>
import { useSessionStore } from '~/stores/session'
const session = useSessionStore()
const api = useApi()
const route = useRoute()
const error = ref('')
const busy = ref(true)
const login = ref('')
const password = ref('')
async function connect() {
  busy.value = true
  error.value = ''
  try {
    if (!session.csrf_token) session.apply(await api('/auth/session'))
    session.apply(
      await api('/auth/login', {
        method: 'POST',
        body: { login: login.value, password: password.value },
      }),
    )
    password.value = ''
    remember(TRIED, null)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
const oidc = ref({ enabled: false, provider: '', only: false })
const KEY = 'animmalle:oidc'
const base64url = (bytes) =>
  btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
// PKCE : le fournisseur ne reçoit que l'empreinte du code_verifier, conservé dans l'onglet
const TRIED = 'animmalle:oidc_tried'
const remember = (key, value) => {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    // sans stockage, la connexion silencieuse n'est pas tentée
  }
}
// Connexion sans interaction d'un visiteur déjà connecté chez le fournisseur : une seule tentative
// par onglet entre deux connexions, donc jamais de boucle de redirections.
async function trySilentOidc() {
  try {
    if (sessionStorage.getItem(TRIED)) return false
    remember(TRIED, '1')
    if (sessionStorage.getItem(TRIED) !== '1') return false
  } catch {
    return false
  }
  return connectOidc(true)
}
async function connectOidc(silent = false) {
  error.value = ''
  try {
    const state = base64url(crypto.getRandomValues(new Uint8Array(16)))
    const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)))
    const digest = await crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(verifier),
    )
    const { url } = await api('/auth/oidc/authorize', {
      query: {
        state,
        code_challenge: base64url(new Uint8Array(digest)),
        ...(silent ? { silent: 1 } : {}),
      },
    })
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ state, verifier, back: route.fullPath, silent }),
    )
    window.location.assign(url)
    return true
  } catch (e) {
    if (!silent) error.value = e.message
    return false
  }
}
// retour du fournisseur sur /oidc?code=…&state=… (ou ?error=…)
async function finishOidc() {
  let saved = null
  try {
    saved = JSON.parse(sessionStorage.getItem(KEY))
    sessionStorage.removeItem(KEY)
  } catch {
    saved = null
  }
  const code = route.query.code
  // connexion silencieuse sans succès (pas connecté chez le fournisseur) : page de connexion, sans erreur
  if (
    saved?.silent &&
    saved.state === route.query.state &&
    typeof code !== 'string'
  ) {
    return navigateTo('/', { replace: true })
  }
  if (!saved || saved.state !== route.query.state || typeof code !== 'string') {
    error.value = 'La connexion a été refusée ou a expiré. Réessayez.'
    return navigateTo('/', { replace: true })
  }
  if (!session.csrf_token) session.apply(await api('/auth/session'))
  const data = await api('/auth/oidc/callback', {
    method: 'POST',
    body: { code, code_verifier: saved.verifier },
  })
  const back =
    saved.back.startsWith('/') &&
    !saved.back.startsWith('//') &&
    !saved.back.startsWith('/oidc')
      ? saved.back
      : '/'
  await navigateTo(back, { replace: true })
  remember(TRIED, null) // une future perte de session pourra être rattrapée
  session.apply(data)
}
async function logout() {
  error.value = ''
  try {
    await api('/auth/logout', { method: 'POST' })
    remember(TRIED, '1') // déconnexion voulue : pas de reconnexion silencieuse dans cet onglet
    session.clear()
    await navigateTo('/')
  } catch (e) {
    error.value = e.message
  }
}
// Recherche générale : la saisie reste affichée sur la page des résultats.
const searchText = ref('')
watch(
  () => [route.path, route.query.q],
  ([path, q]) => {
    if (path === '/search') searchText.value = typeof q === 'string' ? q : ''
  },
  { immediate: true },
)
async function submitSearch() {
  const q = searchText.value.trim()
  if (q) await navigateTo({ path: '/search', query: { q } })
}
onMounted(() => {
  const el = document.querySelector('body header')
  if (!el || typeof ResizeObserver === 'undefined') return
  new ResizeObserver(() => {
    document.documentElement.style.setProperty(
      '--site-h',
      `${el.offsetHeight}px`,
    )
  }).observe(el)
})
onMounted(async () => {
  try {
    const returning = route.path === '/oidc'
    if (returning) await finishOidc()
    else session.apply(await api('/auth/session'))
    if (!session.user) {
      oidc.value = await api('/auth/oidc/config').catch(() => oidc.value)
      // le navigateur part chez le fournisseur : on garde l'écran de chargement
      if (oidc.value.enabled && !returning && (await trySilentOidc())) return
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
})
</script>
<template>
  <a class="skip" href="#content">Aller au contenu</a>
  <header>
    <NuxtLink class="brand" to="/"
      ><span
        >Anim’Malle <small>Parc national des Cévennes</small></span
      ></NuxtLink
    >
    <nav v-if="session.user" class="topnav" aria-label="Navigation principale">
      <NuxtLink to="/">Accueil</NuxtLink>
      <NuxtLink to="/animations">Pédathèque</NuxtLink>
      <NuxtLink to="/materials">Médiathèque</NuxtLink>
      <NuxtLink to="/outils">Outils facilitateurs</NuxtLink>
      <NuxtLink to="/stats">Statistiques</NuxtLink>
      <NuxtLink v-if="session.can_edit_thesaurus" to="/thesaurus"
        >Thésaurus</NuxtLink
      >
    </nav>
    <form
      v-if="session.user"
      class="site-search"
      role="search"
      @submit.prevent="submitSearch"
    >
      <input
        v-model="searchText"
        type="search"
        maxlength="200"
        placeholder="Rechercher partout…"
        aria-label="Recherche générale : pédathèque, outils facilitateurs et médiathèque"
      />
      <button type="submit" aria-label="Lancer la recherche">
        <i class="pi pi-search" aria-hidden="true" />
      </button>
    </form>
    <div v-if="session.user" class="userbox">
      <span class="avatar" aria-hidden="true">{{ initials }}</span>
      <span class="name">{{ firstName }}</span>
      <PButton class="linkbtn" label="Se déconnecter" @click="logout" />
    </div>
  </header>
  <main id="content">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="busy" role="status">Chargement de la session…</p>
    <section v-else-if="!session.user" class="login card">
      <p class="eyebrow">Bienvenue dans la malle pédagogique</p>
      <h1>Content de vous revoir.</h1>
      <p class="muted">
        Connectez-vous pour consulter et enrichir les ressources de l’équipe.
      </p>
      <PButton
        v-if="oidc.enabled"
        class="oidc-button"
        type="button"
        :label="`Se connecter avec ${oidc.provider}`"
        @click="connectOidc()"
      />
      <p v-if="oidc.enabled && !oidc.only" class="muted">ou</p>
      <form v-if="!oidc.only" @submit.prevent="connect">
        <label
          >Identifiant<input
            v-model="login"
            autocomplete="username"
            required /></label
        ><label
          >Mot de passe<input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required /></label
        ><PButton type="submit" label="Se connecter" :disabled="busy" />
      </form>
    </section>
    <NuxtPage v-else :key="route.path" />
  </main>
  <ConfirmDeleteDialog />
  <footer>
    <span>Anim’Malle · Les ressources pédagogiques des Cévennes</span
    ><span>Bonne animation !</span>
  </footer>
</template>
