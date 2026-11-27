<script setup>
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import TextAlign from '@tiptap/extension-text-align'
import { Color, FontSize, TextStyle } from '@tiptap/extension-text-style'
import { TableKit } from '@tiptap/extension-table'
import { Node } from '@tiptap/core'
import { toRichHtml } from '../../lib/richtext.mjs'

// Éditeur WYSIWYG ; sa hauteur suit son contenu (3 lignes au minimum).
const model = defineModel({ type: String, default: '' })
// simple : barre réduite (gras, italique, souligné, liste à puces, smiley).
const props = defineProps({ label: String, simple: Boolean })

// Icône PrimeIcons insérée dans le texte (<i class="pi pi-xxx">).
const CLASSE_ICONE = /^pi pi-[a-z0-9-]+$/
const Icone = Node.create({
  name: 'icone',
  group: 'inline',
  inline: true,
  atom: true,
  addAttributes() {
    return { classe: { default: null, parseHTML: (element) => element.className.trim() } }
  },
  parseHTML() {
    return [
      {
        tag: 'i',
        priority: 60,
        getAttrs: (element) => (CLASSE_ICONE.test(element.className.trim()) ? null : false)
      }
    ]
  },
  renderHTML({ node }) {
    return ['i', { class: node.attrs.classe, 'aria-hidden': 'true' }]
  }
})

const html = (editor) => (editor.isEmpty ? '' : editor.getHTML())
const editor = useEditor({
  content: toRichHtml(model.value),
  extensions: [
    StarterKit.configure({ link: { openOnClick: false } }),
    TextStyle,
    Color,
    FontSize,
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    TableKit.configure({ table: { resizable: true } }),
    Icone
  ],
  editorProps: {
    attributes: { role: 'textbox', 'aria-multiline': 'true', 'aria-label': props.label || '' }
  },
  onUpdate: ({ editor }) => {
    model.value = html(editor)
  }
})
watch(model, (value) => {
  if (editor.value && value !== html(editor.value))
    editor.value.commands.setContent(toRichHtml(value), { emitUpdate: false })
})
onBeforeUnmount(() => editor.value?.destroy())

const allTools = [
  ['B', 'Gras', 'toggleBold', 'bold'],
  ['I', 'Italique', 'toggleItalic', 'italic'],
  ['U', 'Souligné', 'toggleUnderline', 'underline'],
  ['S', 'Barré', 'toggleStrike', 'strike'],
  ['•', 'Liste à puces', 'toggleBulletList', 'bulletList'],
  ['1.', 'Liste numérotée', 'toggleOrderedList', 'orderedList'],
  ['❝', 'Citation', 'toggleBlockquote', 'blockquote']
]
const SIMPLE_TOOLS = ['bold', 'italic', 'underline', 'bulletList']
const tools = computed(() =>
  props.simple ? allTools.filter(([, , , name]) => SIMPLE_TOOLS.includes(name)) : allTools
)
const aligns = [
  ['left', 'Aligner à gauche', 'pi-align-left'],
  ['center', 'Aligner au centre', 'pi-align-center'],
  ['right', 'Aligner à droite', 'pi-align-right']
]
const colors = [
  '#000000', '#4d4d4d', '#808080', '#c0392b', '#e67e22', '#f1c40f',
  '#27ae60', '#16a085', '#2980b9', '#8e44ad', '#d81b60'
]
const smileys = [
  '😀', '😃', '😄', '😁', '😅', '😂', '🙂', '😉', '😊', '😍', '😎', '🤔', '😮', '😢', '😡', '🙄',
  '👍', '👎', '👏', '🙌', '💪', '🎉', '🎈', '🎲', '⭐', '❤️', '✅', '❌', '⚠️', '💡', '❓', '❗'
]
const icons = [
  'star', 'heart', 'check', 'bell', 'bookmark', 'calendar', 'clock', 'stopwatch', 'hourglass',
  'comment', 'info-circle', 'exclamation-triangle', 'question-circle', 'lightbulb', 'users', 'user',
  'flag', 'home', 'map-marker', 'megaphone', 'book', 'camera', 'video', 'image', 'microphone',
  'cog', 'wrench', 'search', 'shield', 'sun', 'moon', 'bolt', 'gift', 'trophy', 'thumbs-up', 'eye',
  'file', 'folder', 'link', 'key', 'tag', 'palette', 'pencil', 'play', 'pause', 'truck', 'globe',
  'compass', 'crown', 'sparkles', 'verified', 'print', 'envelope', 'phone', 'arrow-right'
]
const sizes = [
  ['Petit', '0.85em'],
  ['Normal', ''],
  ['Grand', '1.25em'],
  ['Très grand', '1.5em'],
  ['Énorme', '2em']
]
const size = computed({
  get: () => editor.value?.getAttributes('textStyle').fontSize || '',
  set(value) {
    const chain = editor.value.chain().focus()
    if (value) chain.setFontSize(value).run()
    else chain.unsetFontSize().run()
  }
})
const panel = ref(null)
const toggle = (name) => (panel.value = panel.value === name ? null : name)
const setColor = (color) => {
  const chain = editor.value.chain().focus()
  if (color) chain.setColor(color).run()
  else chain.unsetColor().run()
  panel.value = null
}
const insertSmiley = (smiley) => {
  editor.value.chain().focus().insertContent(smiley).run()
  panel.value = null
}
const insertIcon = (name) => {
  editor.value.chain().focus().insertContent({ type: 'icone', attrs: { classe: `pi pi-${name}` } }).run()
  panel.value = null
}
const clearFormat = () =>
  editor.value.chain().focus().unsetAllMarks().clearNodes().unsetTextAlign().run()
const tableTools = [
  ['+ Ligne', 'Ajouter une ligne en dessous', 'addRowAfter'],
  ['+ Colonne', 'Ajouter une colonne à droite', 'addColumnAfter'],
  ['− Ligne', 'Supprimer la ligne', 'deleteRow'],
  ['− Colonne', 'Supprimer la colonne', 'deleteColumn'],
  ['Ligne de titre', 'Mettre ou retirer la ligne de titre', 'toggleHeaderRow'],
  ['Supprimer le tableau', 'Supprimer le tableau', 'deleteTable']
]
const insertTable = () =>
  editor.value.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
const run = (command) => editor.value.chain().focus()[command]().run()
function link() {
  const current = editor.value.getAttributes('link').href || ''
  const href = window.prompt('Adresse du lien (vide pour le retirer)', current)
  if (href === null) return
  const chain = editor.value.chain().focus().extendMarkRange('link')
  if (href.trim()) chain.setLink({ href: href.trim() }).run()
  else chain.unsetLink().run()
}
</script>
<template>
  <div v-if="editor" class="rich">
    <div class="rich-tools" role="toolbar" :aria-label="`Mise en forme : ${label || ''}`">
      <button
        v-for="[text, title, command, name] in tools"
        :key="name"
        type="button"
        :title="title"
        :aria-label="title"
        :aria-pressed="editor.isActive(name)"
        :class="{ on: editor.isActive(name) }"
        @click="run(command)"
      >{{ text }}</button>
      <template v-if="!simple">
      <button
        v-for="[value, title, icon] in aligns"
        :key="value"
        type="button"
        :title="title"
        :aria-label="title"
        :class="{ on: editor.isActive({ textAlign: value }) }"
        @click="editor.chain().focus().setTextAlign(value).run()"
      ><i :class="['pi', icon]" aria-hidden="true" /></button>
      <select v-model="size" class="rich-size" title="Taille du texte" aria-label="Taille du texte">
        <option v-for="[name, value] in sizes" :key="value" :value="value">{{ name }}</option>
      </select>
      <span class="rich-pop">
        <button type="button" title="Couleur du texte" aria-label="Couleur du texte" @click="toggle('color')">
          <span class="rich-color" :style="{ borderColor: editor.getAttributes('textStyle').color || 'currentColor' }">A</span>
        </button>
        <div v-if="panel === 'color'" class="rich-panel">
          <button
            v-for="color in colors"
            :key="color"
            type="button"
            class="rich-swatch"
            :style="{ background: color }"
            :title="color"
            :aria-label="`Couleur ${color}`"
            @click="setColor(color)"
          />
          <button type="button" @click="setColor(null)">Aucune</button>
        </div>
      </span>
      </template>
      <span class="rich-pop">
        <button type="button" title="Insérer un smiley" aria-label="Insérer un smiley" @click="toggle('smiley')">🙂</button>
        <div v-if="panel === 'smiley'" class="rich-panel">
          <button v-for="smiley in smileys" :key="smiley" type="button" @click="insertSmiley(smiley)">{{ smiley }}</button>
        </div>
      </span>
      <template v-if="!simple">
      <span class="rich-pop">
        <button type="button" title="Insérer une icône" aria-label="Insérer une icône" @click="toggle('icon')">
          <i class="pi pi-star" aria-hidden="true" />
        </button>
        <div v-if="panel === 'icon'" class="rich-panel">
          <button v-for="name in icons" :key="name" type="button" :title="name" :aria-label="name" @click="insertIcon(name)">
            <i :class="`pi pi-${name}`" aria-hidden="true" />
          </button>
        </div>
      </span>
      <button type="button" title="Ligne de séparation" aria-label="Ligne de séparation" @click="run('setHorizontalRule')">
        <i class="pi pi-minus" aria-hidden="true" />
      </button>
      <button type="button" title="Insérer un tableau" aria-label="Insérer un tableau" @click="insertTable">
        <i class="pi pi-table" aria-hidden="true" />
      </button>
      <button type="button" title="Effacer la mise en forme" aria-label="Effacer la mise en forme" @click="clearFormat">
        <i class="pi pi-eraser" aria-hidden="true" />
      </button>
      <button type="button" title="Lien" aria-label="Lien" :class="{ on: editor.isActive('link') }" @click="link">🔗</button>
      </template>
    </div>
    <div v-if="editor.isActive('table')" class="rich-tools rich-table-tools">
      <button v-for="[text, title, command] in tableTools" :key="command" type="button" :title="title" @click="run(command)">
        {{ text }}
      </button>
    </div>
    <EditorContent :editor="editor" class="rich-body" />
  </div>
</template>
