import { test, expect } from '@playwright/test'

async function fixture(page, admin = true) {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'warning' && message.text().includes('[Vue warn]'))
      errors.push(message.text())
  })
  let logged = false
  let animation = null
  let material = null
  let comments = []
  const calls = []
  const tags = [
    ['ref.type_seq', 'Partie'],
    ['ref.approches', 'Approche'],
    ['ref.modalites', 'Modalité'],
    ['ref.duree', 'Durée totale'],
    ['ref.type_mat', 'Photo'],
    ['ref.type_outil', 'Débats'],
    ['ref.difficulte', 'Facile'],
    ['ref.thematiques', 'Faune']
  ].map(([reference, label], index) => ({
    id: index + 1,
    reference,
    label,
    code: reference === 'ref.type_outil' ? 'debats' : ''
  }))
  await page.route(
    'https://api.animmalle.example.org/api/**',
    async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname.replace('/api', '')
      const method = request.method()
      calls.push({
        path,
        method,
        headers: request.headers(),
        body: request.postData()
      })
      const response = (data) =>
        route.fulfill({
          json: data,
          headers: {
            'Access-Control-Allow-Origin': 'http://127.0.0.1:3107',
            'Access-Control-Allow-Credentials': 'true'
          }
        })
      if (method === 'OPTIONS')
        return route.fulfill({
          status: 204,
          headers: {
            'Access-Control-Allow-Origin': 'http://127.0.0.1:3107',
            'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Headers': 'Content-Type,X-CSRF-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE'
          }
        })
      if (path === '/auth/login') {
        logged = true
        return response({
          user: { name: 'Alice', groups: [] },
          is_admin: admin,
          can_edit_thesaurus: admin,
          csrf_token: 'rotated-token'
        })
      }
      if (path === '/auth/session')
        return response({
          user: logged ? { name: 'Alice' } : null,
          is_admin: admin,
          can_edit_thesaurus: admin,
          csrf_token: 'initial-token'
        })
      if (path === '/thesaurus') return response({ items: tags })
      if (path === '/authors' || path === '/users')
        return response({ items: ['Alice'] })
      if (path === '/animations' && method === 'POST') {
        animation = {
          ...request.postDataJSON(),
          id: 'demo',
          auteurs: 'Alice',
          date_modif: '2026-11-05'
        }
        return response(animation)
      }
      if (path === '/animations')
        return response({
          items: animation ? [animation] : [],
          total: animation ? 1 : 0
        })
      if (path === '/animations/demo/comments' && method === 'POST') {
        comments.push({ ...request.postDataJSON(), id: 1, auteur: 'Alice' })
        return response(comments.at(-1))
      }
      if (path === '/animations/demo/comments')
        return response({ items: comments })
      if (path === '/animations/demo' && method === 'PUT') {
        animation = { ...animation, ...request.postDataJSON() }
        return response(animation)
      }
      if (path === '/animations/demo') return response(animation)
      if (path === '/media' && method === 'POST') {
        material = {
          id: 1,
          nom: 'Média test',
          description: 'Une image',
          fk_type_mat_id: 5,
          thematiques: [],
          has_file: true
        }
        return response(material)
      }
      if (path === '/media')
        return response({
          items: material ? [material] : [],
          total: material ? 1 : 0
        })
      if (path === '/media/1/file')
        return route.fulfill({
          body: 'test media',
          contentType: 'application/octet-stream',
          headers: {
            'Content-Disposition': 'attachment; filename="test.txt"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
          }
        })
      if (path === '/media/1') return response(material)
      if (path === '/pages/debats')
        return response({
          contenu: '## Débats',
          html: '<h2>Débats</h2>',
          documents: []
        })
      return route.fulfill({
        status: 404,
        json: { error: { message: 'Ressource introuvable.' } }
      })
    }
  )
  await page.goto('/')
  expect(await page.content()).not.toContain('centralConfigPath')
  expect(await page.content()).not.toContain('postgresql')
  await page.getByLabel('Identifiant', { exact: true }).fill('alice')
  await page.getByLabel('Mot de passe', { exact: true }).fill('secret')
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('navigation')).toBeVisible()
  return { errors, calls }
}

test('Connexion, création ordonnée, modification et commentaire avec rotation CSRF', async ({
  page
}) => {
  const { errors, calls } = await fixture(page)
  await page.getByRole('link', { name: 'Préparer une animation' }).click()
  await page.getByLabel('Titre *', { exact: true }).fill('Découvrir la forêt')
  await page.getByRole('button', { name: 'Ajouter une séquence' }).click()
  await page
    .getByLabel('Titre de la séquence *', { exact: true })
    .fill('Écouter')
  for (const [label, value] of [
    ['Partie *', '1'],
    ['Approche *', '2'],
    ['Modalité *', '3']
  ])
    await page.getByLabel(label, { exact: true }).selectOption(value)
  await page.getByLabel('Durée (minutes) *', { exact: true }).fill('10')
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Découvrir la forêt', exact: true })
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: '1. Écouter', exact: true })
  ).toBeVisible()
  const creation = calls.find(
    (call) => call.path === '/animations' && call.method === 'POST'
  )
  expect(creation.headers['x-csrf-token']).toBe('rotated-token')
  expect(
    calls.find((call) => call.path === '/auth/login').headers['x-csrf-token']
  ).toBe('initial-token')
  await page.getByRole('button', { name: 'Modifier', exact: true }).click()
  await page.getByLabel('Titre *', { exact: true }).fill('La forêt vivante')
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'La forêt vivante', exact: true })
  ).toBeVisible()
  await page.getByLabel('Votre commentaire').fill('À tester au printemps')
  await page.getByRole('button', { name: 'Publier', exact: true }).click()
  await expect(
    page.getByText('À tester au printemps', { exact: true })
  ).toBeVisible()
  await page.screenshot({ path: 'test-results/animation.png', fullPage: true })
  expect(errors).toEqual([])
})

test('Médiathèque, formulaire multipart, téléchargement et pages outils', async ({
  page
}) => {
  const { errors, calls } = await fixture(page)
  await page.getByRole('link', { name: 'Médiathèque', exact: true }).click()
  await page.getByRole('link', { name: 'Importer une ressource' }).click()
  await page.getByLabel('Nom *', { exact: true }).fill('Média test')
  await page.getByLabel('Type *', { exact: true }).selectOption('5')
  await page.getByLabel('Pièce jointe', { exact: true }).setInputFiles({
    name: 'test.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('test')
  })
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Média test', exact: true })
  ).toBeVisible()
  expect(
    calls.find((call) => call.path === '/media' && call.method === 'POST')
      .headers['content-type']
  ).toContain('multipart/form-data')
  const download = page.waitForEvent('download')
  await page
    .getByRole('button', { name: 'Télécharger la pièce jointe', exact: true })
    .click()
  expect((await download).suggestedFilename()).toBe('test.txt')
  await page
    .getByRole('link', { name: 'Outils facilitateurs', exact: true })
    .click()
  await page.getByRole('link', { name: 'Débats', exact: true }).click()
  await expect(page.locator('.page-html h2')).toHaveText('Débats')
  expect(errors).toEqual([])
})

test('Droits visibles, erreur de validation et disposition mobile', async ({
  page
}) => {
  const { errors } = await fixture(page, false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: 'test-results/accueil-mobile.png',
    fullPage: true
  })
  await expect(
    page.getByRole('link', { name: 'Thésaurus', exact: true })
  ).toHaveCount(0)
  await page.getByRole('link', { name: 'Pédathèque', exact: true }).click()
  await expect(
    page.getByText('Aucune ressource pour ces critères.')
  ).toBeVisible()
  await page
    .getByRole('link', { name: 'Créer une animation', exact: true })
    .click()
  await page.getByLabel('Titre *', { exact: true }).fill('Brouillon')
  await page.route('**/api/animations', (route) =>
    route.fulfill({
      status: 422,
      json: {
        error: {
          message: 'Validation impossible',
          fields: { titre: ['Déjà utilisé'] }
        }
      }
    })
  )
  await page.getByRole('button', { name: 'Enregistrer', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Validation impossible')
  await expect(page.getByLabel('Titre *', { exact: true })).toHaveValue(
    'Brouillon'
  )
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth
    )
  ).toBe(true)
  expect(errors).toEqual([])
})
