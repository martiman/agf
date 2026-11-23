import { t, locale, srv } from "../i18n.js";
import { store, loadIdeas } from "../store.js";
import { ideasApi, copyText } from "../api.js";

const P = (d) => ["path", { d }];
const ICONS = {
  check: [P("M20 6 9 17l-5-5")],
  undo: [P("M3 7v6h6"), P("M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13")],
  edit: [P("M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z")],
  copy: [["rect", { width: 14, height: 14, x: 8, y: 8, rx: 2, ry: 2 }], P("M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2")],
  trash: [P("M3 6h18"), P("M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"), P("M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2")],
  open: [P("M15 3h6v6"), P("M10 14 21 3"), P("M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6")],
  chat: [P("M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z")],
  search: [["circle", { cx: 11, cy: 11, r: 8 }], P("m21 21-4.3-4.3")],
  grid: [["rect", { width: 7, height: 7, x: 3, y: 3, rx: 1 }], ["rect", { width: 7, height: 7, x: 14, y: 3, rx: 1 }], ["rect", { width: 7, height: 7, x: 14, y: 14, rx: 1 }], ["rect", { width: 7, height: 7, x: 3, y: 14, rx: 1 }]],
  list: [P("M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01")],
  plus: [P("M5 12h14"), P("M12 5v14")],
  bulb: [P("M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"), P("M9 18h6"), P("M10 22h4")],
};
const Ico = { props: { n: String, size: { type: Number, default: 18 } },
  render() { return Vue.h("svg", { viewBox: "0 0 24 24", width: this.size, height: this.size, fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" },
    (ICONS[this.n] || []).map(([tag, a]) => Vue.h(tag, a))); } };

export default {
  components: { Ico },
  setup() {
    const q = Vue.ref(""), status = Vue.ref("open"), editing = Vue.ref(""), draft = Vue.ref(""), openCtx = Vue.reactive({}), full = Vue.reactive({});
    const mode = Vue.ref(localStorage.getItem("flow.ideasView") === "cards" ? "cards" : "list");
    const setMode = m => { mode.value = m; try { localStorage.setItem("flow.ideasView", m); } catch (e) {  } };
    const note = Vue.reactive({ open: false, text: "", busy: false });
    const list = Vue.computed(() => {
      const t = q.value.trim().toLowerCase();
      return store.ideas.filter(i => i.status === status.value && (!t || (i.text + " " + (i.context || "") + " " + ((i.source || {}).title || "")).toLowerCase().includes(t)))
        .slice().sort((a, b) => b.created - a.created);
    });
    const nOpen = Vue.computed(() => store.ideas.filter(i => i.status === "open").length);
    const nDone = Vue.computed(() => store.ideas.filter(i => i.status === "done").length);
    const call = async body => { const r = await ideasApi(body); if (!r.ok) antd.message.error(srv(r.error_k, r.error) || t("ideas.err_status", { status: r.status })); await loadIdeas(); return r; };
    const addNote = async () => {
      if (!note.text.trim()) return;
      note.busy = true; const r = await call({ action: "add", text: note.text }); note.busy = false;
      if (r.ok) { note.text = ""; note.open = false; status.value = "open"; }
    };
    const setDone = (i, done) => call({ action: "update", id: i.id, status: done ? "done" : "open" });
    const edit = i => { editing.value = i.id; draft.value = i.text; };
    const save = async i => { if ((await call({ action: "update", id: i.id, text: draft.value })).ok) editing.value = ""; };
    const remove = i => antd.Modal.confirm({ title: t("ideas.delete_title"), content: i.text.slice(0, 160), okText: t("ideas.delete"), okType: "danger", cancelText: t("ant.cancel"), onOk: () => call({ action: "delete", id: i.id }) });
    const copy = async i => { const ok = await copyText(i.text + (i.source && i.source.ticket ? t("ideas.copy_origin", { ticket: i.source.ticket }) : "")); antd.message[ok ? "success" : "warning"](t(ok ? "ideas.copied" : "ideas.copy_blocked")); };
    const parts = i => { const t = (i.source || {}).title || ""; return t && i.text.startsWith(t + ": ") ? { title: t, body: i.text.slice(t.length + 2) } : { title: "", body: i.text }; };
    const repo = i => ((i.source || {}).cwd || "").split("/").pop();
    const when = i => { const l = (i.source || {}).last; return l ? new Date(l).toLocaleDateString(locale(), { day: "numeric", month: "numeric", year: "numeric" }) : ""; };
    const sessLink = i => { const id = (i.source || {}).session_id; return /^local_[0-9a-f-]{36}$/.test(id || "") ? "claude://claude.ai/epitaxy/" + id : null; };
    Vue.watch(() => store.view, v => { if (v === "ideas") loadIdeas(); }, { immediate: true });
    return { mode, setMode, store, q, status, editing, draft, openCtx, full, note, list, nOpen, nDone, addNote, setDone, edit, save, remove, copy, parts, repo, when, sessLink };
  },
  template: `
  <div class="scroll ideas-page">
    <div class="ideas-top">
      <label class="gsearch"><Ico n="search" :size="18" /><input v-model="q" :placeholder="$t('ideas.search')" :aria-label="$t('ideas.search')" /></label>
      <div class="seg" role="tablist"><button role="tab" :class="{ on: status === 'open' }" @click="status = 'open'">{{ $t('ideas.tab.open') }} <b>{{ nOpen }}</b></button><button role="tab" :class="{ on: status === 'done' }" @click="status = 'done'">{{ $t('ideas.tab.done') }} <b>{{ nDone }}</b></button></div>
      <div class="vtoggle"><button class="kbtn" :class="{ on: mode === 'cards' }" :title="$t('ideas.view.cards')" :aria-label="$t('ideas.view.cards_aria')" :aria-pressed="mode === 'cards'" @click="setMode('cards')"><Ico n="grid" :size="18" /></button>
        <button class="kbtn" :class="{ on: mode === 'list' }" :title="$t('ideas.view.list')" :aria-label="$t('ideas.view.list_aria')" :aria-pressed="mode === 'list'" @click="setMode('list')"><Ico n="list" :size="18" /></button></div>
    </div>
    <div v-if="!list.length" class="ideas-empty"><Ico n="bulb" :size="64" /><div>{{ $t(store.ideas.length ? (q ? 'ideas.empty.search' : status === 'open' ? 'ideas.empty.all_done' : 'ideas.empty.none_done') : 'ideas.empty.none') }}</div>
      <div v-if="!store.ideas.length" class="muted sm">{{ $t('ideas.empty.hint') }}</div></div>
    <div v-else-if="mode === 'cards'" class="keep-grid">
      <article v-for="i in list" :key="i.id" class="kcard" :class="{ done: i.status === 'done', editing: editing === i.id }">
        <div v-if="editing === i.id"><textarea v-model="draft" class="k-edit" rows="5" maxlength="2000" :aria-label="$t('ideas.edit_aria')"></textarea>
          <div class="k-bar always"><span></span><span><button class="alink" @click="editing = ''">{{ $t('ant.cancel') }}</button><button class="alink strong" @click="save(i)">{{ $t('ideas.save') }}</button></span></div></div>
        <template v-else>
          <h3 v-if="parts(i).title" class="k-title">{{ parts(i).title }}</h3>
          <p class="k-body" :class="{ clamp: !full[i.id] }" @click="full[i.id] = !full[i.id]" :title="full[i.id] ? '' : $t('ideas.expand_tip')">{{ parts(i).body }}</p>
          <div v-if="openCtx[i.id] && i.context" class="k-ctx"><b>{{ $t('ideas.last_reply') }}</b>{{ i.context }}</div>
          <div class="k-chips"><span v-if="repo(i)" class="kchip">{{ repo(i) }}</span><span v-if="(i.source || {}).ticket" class="kchip">{{ i.source.ticket }}</span><span v-if="when(i)" class="kchip plain">{{ when(i) }}</span></div>
          <div class="k-bar">
            <button class="kbtn" :title="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" :aria-label="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" @click="setDone(i, i.status === 'open')"><Ico :n="i.status === 'open' ? 'check' : 'undo'" :size="16" /></button>
            <button class="kbtn" :title="$t('ideas.edit')" :aria-label="$t('ideas.edit')" @click="edit(i)"><Ico n="edit" :size="16" /></button>
            <button class="kbtn" :title="$t('ideas.copy')" :aria-label="$t('ideas.copy')" @click="copy(i)"><Ico n="copy" :size="16" /></button>
            <button v-if="i.context" class="kbtn" :class="{ on: openCtx[i.id] }" :title="$t('ideas.last_reply')" :aria-label="$t('ideas.last_reply')" @click="openCtx[i.id] = !openCtx[i.id]"><Ico n="chat" :size="16" /></button>
            <a v-if="sessLink(i)" class="kbtn" :href="sessLink(i)" :title="$t('ideas.open_session')" :aria-label="$t('ideas.open_session_aria')"><Ico n="open" :size="16" /></a>
            <span class="grow"></span>
            <button class="kbtn" :title="$t('ideas.delete')" :aria-label="$t('ideas.delete')" @click="remove(i)"><Ico n="trash" :size="16" /></button>
          </div>
        </template>
      </article>
    </div>
    <div v-else class="klist" role="list">
      <div v-for="i in list" :key="i.id" class="krow" :class="{ done: i.status === 'done', open: full[i.id] || editing === i.id }" role="listitem" @click="editing !== i.id && (full[i.id] = !full[i.id])">
        <span class="kr-chk" @click.stop><button class="kbtn" :title="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" :aria-label="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" @click="setDone(i, i.status === 'open')"><Ico :n="i.status === 'open' ? 'check' : 'undo'" :size="16" /></button></span>
        <div class="kr-main">
          <div v-if="editing === i.id" @click.stop><textarea v-model="draft" class="k-edit" rows="4" maxlength="2000" :aria-label="$t('ideas.edit_aria')"></textarea>
            <div class="k-bar always"><span></span><span><button class="alink" @click="editing = ''">{{ $t('ant.cancel') }}</button><button class="alink strong" @click="save(i)">{{ $t('ideas.save') }}</button></span></div></div>
          <template v-else><div class="kr-line"><span v-if="parts(i).title" class="kr-title">{{ parts(i).title }}</span><span class="kr-body">{{ parts(i).body }}</span></div>
            <div v-if="openCtx[i.id] && i.context" class="k-ctx" @click.stop><b>{{ $t('ideas.last_reply') }}</b>{{ i.context }}</div></template>
        </div>
        <span v-if="editing !== i.id" class="kr-meta"><span v-if="repo(i)" class="kchip">{{ repo(i) }}</span><span v-if="(i.source || {}).ticket" class="kchip">{{ i.source.ticket }}</span><span class="kr-date">{{ when(i) }}</span></span>
        <span v-if="editing !== i.id" class="kr-acts" @click.stop><button class="kbtn" :title="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" :aria-label="$t(i.status === 'open' ? 'ideas.done' : 'ideas.reopen')" @click="setDone(i, i.status === 'open')"><Ico :n="i.status === 'open' ? 'check' : 'undo'" :size="16" /></button>
            <button class="kbtn" :title="$t('ideas.edit')" :aria-label="$t('ideas.edit')" @click="edit(i)"><Ico n="edit" :size="16" /></button>
            <button class="kbtn" :title="$t('ideas.copy')" :aria-label="$t('ideas.copy')" @click="copy(i)"><Ico n="copy" :size="16" /></button>
            <button v-if="i.context" class="kbtn" :class="{ on: openCtx[i.id] }" :title="$t('ideas.last_reply')" :aria-label="$t('ideas.last_reply')" @click="openCtx[i.id] = !openCtx[i.id]; full[i.id] = true"><Ico n="chat" :size="16" /></button>
            <a v-if="sessLink(i)" class="kbtn" :href="sessLink(i)" :title="$t('ideas.open_session')" :aria-label="$t('ideas.open_session_aria')" @click.stop><Ico n="open" :size="16" /></a>
            <button class="kbtn" :title="$t('ideas.delete')" :aria-label="$t('ideas.delete')" @click="remove(i)"><Ico n="trash" :size="16" /></button></span>
      </div>
    </div>
    <a-tooltip :title="$t('ideas.add')" placement="left"><button class="fab" :aria-label="$t('ideas.add')" @click="note.open = true"><Ico n="plus" :size="26" /></button></a-tooltip>
    <a-modal v-model:open="note.open" :title="$t('ideas.new')" :ok-text="$t('ideas.save')" :cancel-text="$t('ant.cancel')" :ok-button-props="{ disabled: !note.text.trim(), loading: note.busy }" @ok="addNote" :after-close="() => { note.text = ''; }">
      <a-textarea v-model:value="note.text" :auto-size="{ minRows: 4, maxRows: 12 }" :maxlength="2000" show-count :placeholder="$t('ideas.note_ph')" @keydown.ctrl.enter="addNote" @keydown.meta.enter="addNote" />
      <div class="muted sm" style="margin-top:6px">{{ $t('ideas.ctrl_enter') }}</div></a-modal>
  </div>`,
};
