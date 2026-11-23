import { store, urgent, assignees, me, setAssignee, setSprint, setHours, setView, toggleSide, refresh, selected, shownItems, tickets } from "../store.js";
import { boardModel } from "../domain.js";
import { t, srv, i18n, setLang, locale, antLocale, LANGS } from "../i18n.js";

export default {
  setup() {
    const opts = Vue.computed(() => [{ value: "*", label: t("filter.all") }, { value: "@me", label: t("filter.me") }, { value: "@none", label: t("filter.none") },
      ...assignees.value.filter(a => a !== me.value).map(a => ({ value: a, label: a }))]);
    const nIdeas = Vue.computed(() => store.ideas.filter(i => i.status === "open").length);
    const updated = Vue.computed(() => store.updated ? store.updated.toLocaleTimeString(locale()) : "…");
    const nSessions = Vue.computed(() => store.data ? store.data.sessions.filter(s => s.state !== "closed").length : 0);
    const nBoard = Vue.computed(() => store.data ? boardModel({ sessions: store.data.sessions, tickets: tickets.value, sprint: store.data.sprint || [],
      assignee: store.assignee, me: me.value, useSprint: store.sprint }).nTickets : 0);
    Vue.watch(urgent, n => { document.title = (n ? "(" + n + ") " : "") + "AGF"; }, { immediate: true });

    const onKey = e => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target.matches && e.target.matches("input,textarea,select,[contenteditable]")) return;
      const k = e.key;
      if (k === "?") { e.preventDefault(); store.tips = !store.tips; }
      else if (k === "/" && store.view === "inbox") { const i = document.querySelector(".master input"); if (i) { e.preventDefault(); i.focus(); } }
      else if (k === "l" || k === "L") store.legend = !store.legend;
      else if (k === "i" || k === "I") setView("inbox");
      else if (k === "s" || k === "S") setView("list");
      else if (k === "b" || k === "B") setView("board");
      else if (k === "r" || k === "R") refresh(true);
      else if (k === "Escape") { store.tips = false; store.legend = false; store.detailOpen = false; }
      else if (store.view === "inbox" && ["ArrowDown", "ArrowUp", "j", "k"].includes(k)) {
        const list = shownItems.value; if (!list.length) return;
        e.preventDefault();
        const i = Math.max(0, list.findIndex(x => selected.value && x.id === selected.value.id)), d = (k === "ArrowDown" || k === "j") ? 1 : -1;
        const next = list[Math.min(list.length - 1, Math.max(0, i + d))];
        store.selId = next.id;
      }
    };
    document.addEventListener("keydown", onKey);
    Vue.onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
    const hoursOpts = Vue.computed(() => [6, 24, 48, 168].map(h => ({ value: h, label: h === 168 ? t('filter.days', { n: 7 }) : h + ' h' })));
    const other = Vue.computed(() => LANGS.find(l => l.id !== i18n.lang));
    return { srv, hoursOpts, other, i18n, antLoc: Vue.computed(antLocale), setLang, nIdeas, store, toggleSide, urgent, opts, setView, setAssignee, setSprint, setHours, refresh, updated, selected, nSessions, nBoard };
  },
  template: `
  <a-config-provider :locale="antLoc"><div class="app" :class="{ collapsed: store.collapsed }">
    <aside class="side">
      <div class="brand"><a-tooltip :title="store.collapsed ? $t('shell.expand') : $t('shell.collapse')" placement="right"><button class="ibtn burger" :aria-label="store.collapsed ? $t('shell.expand') : $t('shell.collapse')" :aria-expanded="!store.collapsed" @click="toggleSide"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button></a-tooltip><img class="logo" src="/v2/assets/branding/agf-icon.svg" alt="AGF" title="Agentic Flow" width="28" height="28"><span class="bname">Agentic Flow</span></div>
      <nav class="nav">
        <button class="nav-item" :class="{ on: store.view === 'inbox' }" @click="setView('inbox')" :title="$t('nav.shortcut', { k: 'I' })"><span class="ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg></span><span class="lbl">{{ $t('nav.inbox') }}</span><span class="n" :class="{ hot: urgent }">{{ urgent || '' }}</span></button>
        <button class="nav-item" :class="{ on: store.view === 'list' }" @click="setView('list')" :title="$t('nav.shortcut', { k: 'S' })"><span class="ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg></span><span class="lbl">{{ $t('nav.sessions') }}</span><span class="n">{{ nSessions }}</span></button>
        <button class="nav-item" :class="{ on: store.view === 'board' }" @click="setView('board')" :title="$t('nav.shortcut', { k: 'B' })"><span class="ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M8 7v7"/><path d="M12 7v4"/><path d="M16 7v9"/></svg></span><span class="lbl">{{ $t('nav.board') }}</span><span class="n">{{ nBoard }}</span></button>
        <button class="nav-item" :class="{ on: store.view === 'cleanup' }" @click="setView('cleanup')" :title="$t('nav.cleanup.tip')"><span class="ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg></span><span class="lbl">{{ $t('nav.cleanup') }}</span><span class="n"></span></button>
        <button class="nav-item" :class="{ on: store.view === 'ideas' }" @click="setView('ideas')" :title="$t('nav.ideas.tip')"><span class="ic"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg></span><span class="lbl">{{ $t('nav.ideas') }}</span><span class="n">{{ nIdeas || '' }}</span></button>
      </nav>
      <div class="filters" v-show="!store.collapsed && !['cleanup', 'ideas'].includes(store.view)">
        <h4>{{ $t('filter.title') }}</h4>
        <div class="field"><a-checkbox :checked="store.sprint" @change="e => setSprint(e.target.checked)">{{ $t('filter.sprint') }}</a-checkbox></div>
        <div class="field row"><span class="lbl">{{ $t('filter.assignee') }}</span><a-select size="small" :value="store.assignee" :options="opts" @change="setAssignee" /></div>
        <div class="field row"><span class="lbl">{{ $t('filter.window') }}</span><a-select size="small" :value="store.hours" @change="setHours"
          :options="hoursOpts" /></div>
      </div>
      <div class="foot">
        <div class="btns">
          <a-tooltip :title="$t('shell.refresh')"><button class="ibtn" :class="{ spin: store.loading }" :aria-label="$t('shell.refresh')" @click="refresh(true)"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg></button></a-tooltip>
          <a-tooltip :title="$t('shell.legend')"><button class="ibtn" :aria-label="$t('shell.legend')" @click="store.legend = true"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/></svg></button></a-tooltip>
          <a-tooltip :title="$t('shell.tips')"><button class="ibtn" :aria-label="$t('shell.tips')" @click="store.tips = true"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg></button></a-tooltip>
          <a-tooltip :title="$t('lang.switch')"><button class="ibtn lang" @click="setLang(other.id)">{{ i18n.lang.toUpperCase() }}</button></a-tooltip>
          <a-badge class="live" :title="store.live ? 'live' : 'offline'" :status="store.live ? 'success' : 'default'" :text="(store.live ? 'live' : 'offline') + ' · ' + updated" />
        </div>
      </div>
    </aside>
    <main class="main">
      <a-alert v-if="store.error" type="error" show-icon :message="$t('shell.server_down', { error: store.error })" banner />
      <a-alert v-else-if="store.data && store.data.jira && store.data.jira.reason" type="warning" show-icon banner
        :message="$t('shell.jira_off', { reason: srv(store.data.jira.reason_k, store.data.jira.reason) })" />
      <ListView v-if="store.view === 'list'" />
      <BoardView v-else-if="store.view === 'board'" />
      <CleanupView v-else-if="store.view === 'cleanup'" />
      <IdeasView v-else-if="store.view === 'ideas'" />
      <div v-else-if="!store.narrow" class="split">
        <MasterList />
        <div class="detail"><div class="detail-inner"><TicketDetail v-if="selected" :item="selected" />
          <div v-else class="empty">{{ $t('shell.select') }}</div></div></div>
      </div>
      <div v-else class="scroll"><MasterList narrow />
        <a-drawer :open="store.detailOpen && !!selected" width="100%" :title="selected ? (selected.key || 'Session') : ''" @close="store.detailOpen = false" destroy-on-close>
          <TicketDetail v-if="selected" :item="selected" /></a-drawer></div>
    </main>
    <Legend /><Tips />
  </div></a-config-provider>`,
};
