const HTML_TAG = /<(p|br|ul|ol|li|strong|em|u|a|h[1-6]|b|i|table|hr)(\s[^>]*)?\/?>/i
const escapeHtml = (text) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

// Les textes historiques sont du texte brut : on les convertit en HTML
// (échappé, sauts de ligne conservés) ; le HTML déjà produit par l'éditeur est conservé.
export function toRichHtml(text) {
  if (!text) return ''
  if (HTML_TAG.test(text)) return text
  return text
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, '<br>')}</p>`)
    .join('')
}

// Texte brut d'un contenu (recherche surlignée, aperçus).
export function toPlainText(text) {
  if (!text || !HTML_TAG.test(text)) return text || ''
  return text
    .replace(/<\/(p|li|h[1-6])>|<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .trim()
}
