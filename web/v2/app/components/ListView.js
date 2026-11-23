import { store, tickets, me } from "../store.js";
import { t, locale } from "../i18n.js";
import { listModel, STATE_TIP, LABEL, STATE_ORDER, ageText, sessionTitle, hasAppLink, plainSummary } from "../domain.js";

const CHIP = { waiting: "you", suspect: "bad", running: "agent", idle: "idle", closed: "done" };
const TILES = () => ["waiting", "suspect", "running", "idle", "closed"].map(k => [k, t("list.tile_" + k)]);
export default {
  setup() {
    const filter = Vue.ref("all");
    const m = Vue.computed(() => store.data ? listModel({ sessions: store.data.sessions, tickets: tickets.value, assignee: store.assignee, me: me.value })
      : { attn: [], active: [], closed: [], counts: {} });
    const rows = Vue.computed(() => [...m.value.attn, ...m.value.active.flatMap(g => g.sessions), ...m.value.closed.flatMap(g => g.sessions)]
      .sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state) || a.age_min - b.age_min));
    const shown = Vue.computed(() => {
      const q = (store.q || "").trim().toLowerCase();
      return rows.value.filter(s => (filter.value === "all" || s.state === filter.value)
        && (!q || ((s.ticket || "") + " " + sessionTitle(s) + " " + (s.branch || "")).toLowerCase().includes(q)));
    });
    const open = s => { if (hasAppLink(s)) location.href = s.app_link; };
    const repo = s => (s.cwd || "").split("/").pop() || "—";
    const sub = s => [s.branch || "—", s.session_id.slice(0, 8), s.ticket && tickets.value[s.ticket] ? plainSummary(tickets.value[s.ticket].summary) : ""].filter(Boolean).join(" · ");
    const tiles = Vue.computed(TILES);
    const now = s => s.state === "waiting" ? (s.notification || t("list.now_waiting")) : s.state === "suspect" ? t("list.now_suspect") : s.state === "running" ? (s.last_event ? t("list.now_running_ev", { event: s.last_event }) : t("list.now_running")) : s.state === "idle" ? t("list.now_idle") : t("list.now_closed");
    const lastTitle = s => s.last_ts ? new Date(s.last_ts).toLocaleString(locale()) : "";
    const ageOf = s => s.age_min < 1 ? t("list.just_now") : ageText(s.age_min);
    const rowTitle = s => (s.cwd || "") + (hasAppLink(s) ? t("list.open_tip") : "");
    return { store, m, filter, shown, rows, open, repo, sub, now, lastTitle, ageOf, rowTitle, CHIP, tiles, STATE_TIP, LABEL, ageText, sessionTitle, hasAppLink };
  },
  template: `
  <div class="scroll">
    <div class="phead">
      <div class="prow"><h2>Sessions</h2><a-input-search v-model:value="store.q" :placeholder="$t('list.search_ph')" allow-clear size="small" style="width:260px" /></div>
      <div class="strip">
        <a-tooltip v-for="tl in tiles" :key="tl[0]" :title="STATE_TIP[tl[0]]"><button class="tile" :class="[CHIP[tl[0]], { on: filter === tl[0] }]" @click="filter = filter === tl[0] ? 'all' : tl[0]">
          <span><b>{{ m.counts[tl[0]] || 0 }}</b> {{ tl[1] }}</span></button></a-tooltip>
      </div>
    </div>
    <div v-if="!shown.length" class="empty">{{ rows.length ? $t('list.empty_filter') : $t('list.empty') }}</div>
    <div v-else class="stable">
      <div class="srow head"><span>{{ $t('list.h_state') }}</span><span>{{ $t('list.h_session') }}</span><span class="now">{{ $t('list.h_now') }}</span><span class="rp">{{ $t('list.h_repo') }}</span><span>{{ $t('list.h_last') }}</span></div>
      <div v-for="s in shown" :key="s.session_id" class="srow" :class="{ click: hasAppLink(s) }" @click="open(s)"
        :title="rowTitle(s)">
        <span><span class="bd" :class="CHIP[s.state]"><i class="dot"></i>{{ LABEL[s.state] || s.state }}</span></span>
        <span style="min-width:0"><div class="st"><b v-if="s.ticket">{{ s.ticket }}</b>{{ sessionTitle(s) }}</div><div class="sub muted">{{ sub(s) }}</div></span>
        <span class="now" :class="CHIP[s.state]">{{ now(s) }}</span>
        <span class="sm muted rp">{{ repo(s) }}</span>
        <span class="sm muted" :title="lastTitle(s)">{{ ageOf(s) }}</span>
      </div>
    </div>
    <p class="legendnote">{{ $t('list.legend') }}</p>
  </div>`,
};
