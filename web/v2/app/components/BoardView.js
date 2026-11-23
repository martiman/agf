import { store, tickets, me, setLanes, setScope, clearBoardFilters, setAssignee } from "../store.js";
import { boardModel, boardCols, laneModel, ticketWord, SPEC_COLS, tagsOf, GATE_SHORT, GATE_TIP, specLevel, plainSummary, nextStep, actionFor,
         sessionTitle, hasAppLink, ageText, STATE_COLOR, LABEL, BALL, BALL_TIP, ballOf, COL_SKILL } from "../domain.js";
import { copyText } from "../api.js";
import { t, locale } from "../i18n.js";

export default {
  setup() {
    const args = () => ({ sessions: store.data.sessions, tickets: tickets.value, sprint: store.data.sprint || [], assignee: store.assignee, me: me.value, useSprint: store.sprint });
    const model = Vue.computed(() => store.data ? boardModel({ ...args(), filters: { q: store.bq, types: store.ftypes, epics: store.fepics, labels: store.flabels } })
      : boardModel({ sessions: [], tickets: {} }));
    const facets = Vue.computed(() => {
      const m = store.data ? boardModel(args()) : { cols: {} }, types = new Set(), labels = new Set(), epics = new Map();
      Object.values(m.cols).forEach(l => l.forEach(c => { if (!c.j.status) return; if (c.j.type) types.add(c.j.type); (c.j.labels || []).forEach(x => labels.add(x));
        epics.set(c.j.parent ? c.j.parent.key : "-", c.j.parent ? c.j.parent.key + " " + (c.j.parent.summary || "").slice(0, 40) : t("board.no_epic")); }));
      const o = a => [...a].sort().map(v => ({ value: v, label: v }));
      return { types: o(types), labels: o(labels), epics: [...epics].sort().map(([value, label]) => ({ value, label })) };
    });
    const sprintOpts = Vue.computed(() => [{ value: "open", label: t("board.scope_active") },
      ...((store.data && store.data.sprints) || []).map(x => ({ value: "sprint:" + x.id, label: t(x.state === "future" ? "board.sprint_future" : "board.sprint_active", { name: x.name }) })),
      { value: "backlog", label: t("board.scope_backlog") }]);
    const hiddenByAssignee = Vue.computed(() => !store.data || store.assignee === "*" ? 0 : boardModel({ ...args(), assignee: "*" }).nTickets - boardModel(args()).nTickets);
    const nFilters = Vue.computed(() => (store.bq.trim() ? 1 : 0) + (store.ftypes.length ? 1 : 0) + (store.fepics.length ? 1 : 0) + (store.flabels.length ? 1 : 0));
    const scopeName = Vue.computed(() => (sprintOpts.value.find(o => o.value === store.scope) || {}).label || store.scope);
    const defs = Vue.computed(() => boardCols(model.value));
    const lanes = Vue.computed(() => store.lanes ? laneModel(model.value) : []);
    const drawer = Vue.ref(null);
    const sel = Vue.reactive({});
    const openCard = (t, colId) => { drawer.value = { id: "board:" + t.k, key: t.k, j: t.j, sess: t.sess, colId, type: null, sinceMin: null }; };
    const toggle = (t, col) => { if (sel[t.k]) delete sel[t.k]; else sel[t.k] = col; };
    const colAll = col => { const l = model.value.cols[col].filter(t => t.j.status); const all = l.length && l.every(t => sel[t.k]); l.forEach(t => { if (all) delete sel[t.k]; else sel[t.k] = col; }); };
    const colAllOn = col => { const l = model.value.cols[col].filter(t => t.j.status); return l.length > 0 && l.every(t => sel[t.k]); };
    const picked = Vue.computed(() => Object.entries(sel).map(([k, col]) => {
      const t = (model.value.cols[col] || []).find(x => x.k === k);
      return t && t.j.status ? actionFor(k, t.j, t.sess, col) : null;
    }).filter(Boolean));
    const nSel = Vue.computed(() => Object.keys(sel).length);
    const clear = () => Object.keys(sel).forEach(k => delete sel[k]);
    const copyAll = async () => {
      const ok = await copyText(picked.value.map(a => a.cmd).join("\n"));
      antd.message[ok ? "success" : "warning"](ok ? t("board.copied_all", { n: picked.value.length }) : t("board.clip_blocked"));
    };
    const gridCols = Vue.computed(() => "repeat(" + defs.value.length + ", 272px)");
    const legendScope = Vue.computed(() => store.sprint ? t("board.legend_scope", { n: ((store.data && store.data.sprint) || []).length, scope: scopeName.value }) : "");
    const toggleLane = pk => { store.foldedLanes[pk] = !store.foldedLanes[pk]; };
    return { store, legendScope, hiddenByAssignee, setAssignee, facets, sprintOpts, nFilters, scopeName, setScope, clearBoardFilters, model, defs, lanes, drawer, openCard, toggle, colAll, colAllOn, sel, picked, nSel, clear, copyAll, gridCols, toggleLane, setLanes, ticketWord, COL_SKILL };
  },
  template: `
  <div class="scroll">
    <div class="phead">
      <div class="prow bfilters">
        <h2>{{ $t('board.title') }}</h2><a-checkbox :checked="store.lanes" @change="e => setLanes(e.target.checked)">{{ $t('board.by_epic') }}</a-checkbox>
        <a-input-search v-model:value="store.bq" :placeholder="$t('board.search_ph')" allow-clear size="small" style="width:280px" />
        <a-select size="small" :value="store.scope" :options="sprintOpts" style="width:210px" @change="setScope" :disabled="!store.sprint"
          :title="store.sprint ? $t('board.scope_tip') : $t('board.scope_tip_off')" />
        <a-select size="small" v-model:value="store.ftypes" mode="multiple" :options="facets.types" :placeholder="$t('board.f_type')" :max-tag-count="1" style="min-width:110px" allow-clear />
        <a-select size="small" v-model:value="store.fepics" mode="multiple" :options="facets.epics" :placeholder="$t('board.f_epic')" :max-tag-count="1" style="min-width:150px;max-width:260px" allow-clear option-filter-prop="label" />
        <a-select size="small" v-model:value="store.flabels" mode="multiple" :options="facets.labels" :placeholder="$t('board.f_label')" :max-tag-count="1" style="min-width:120px" allow-clear />
        <a-tooltip v-if="hiddenByAssignee > 0" :title="$t('board.hidden_tip', { n: hiddenByAssignee })">
          <button class="hidden-hint" @click="setAssignee('*')"><b>{{ hiddenByAssignee }}</b> {{ $t('board.hidden_hint') }}</button></a-tooltip>
        <button v-if="nFilters" class="alink" @click="clearBoardFilters">{{ $t('board.clear_filters', { n: nFilters }) }}</button>
      </div>
    </div>
    <div v-if="!store.lanes" class="board">
      <div class="bcol">
        <div class="bhead" :title="$t('board.free_tip')"><span>{{ $t('board.free_title') }}</span><span class="n">{{ model.freeAct.length }}</span></div>
        <div v-if="!model.freeAct.length" class="bnone">—</div>
        <FreeCard v-for="s in model.freeAct" :key="s.session_id" :s="s" />
        <div v-if="model.free.length > model.freeAct.length" class="bnone">{{ $t('board.free_inactive', { n: model.free.length - model.freeAct.length }) }}</div>
      </div>
      <div v-for="col in defs" :key="col.id" class="bcol" :class="['col-' + col.id, { 'step-empty': !model.cols[col.id].length }]">
        <a-tooltip :title="col.who ? $t('board.col_tip_who', { tip: col.tip, who: col.who }) : col.tip"><div class="bhead">
          <a-checkbox v-if="COL_SKILL[col.id] && model.cols[col.id].length" :checked="colAllOn(col.id)" @click.stop @change="colAll(col.id)" />
          <span>{{ col.title }}</span><span class="n">{{ model.cols[col.id].length }}</span>
          <span v-if="COL_SKILL[col.id]" class="skill" :title="$t('board.skill_tip', { skill: COL_SKILL[col.id] })">{{ COL_SKILL[col.id] }}</span></div></a-tooltip>
        <div v-if="!model.cols[col.id].length" class="bnone">—</div>
        <TicketCard v-for="t in model.cols[col.id]" :key="t.k" :t="t" :col="col.id" :checked="!!sel[t.k]" show-parent @open="openCard(t, col.id)" @toggle="toggle(t, col.id)" />
      </div>
    </div>
    <div v-else class="lanes">
      <div class="lrow2 lhdr" :style="{ gridTemplateColumns: gridCols }">
        <div v-for="col in defs" :key="col.id" class="bhead"><span>{{ col.title }}</span><span class="n">{{ model.cols[col.id].length }}</span></div></div>
      <div v-for="L in lanes" :key="L.key" class="lane">
        <div class="ltitle" @click="toggleLane(L.key)"><span>{{ store.foldedLanes[L.key] ? '▸' : '▾' }}</span>
          <a v-if="L.parent" :href="store.data.jira_base + '/browse/' + L.key" target="_blank" rel="noopener noreferrer" @click.stop>{{ L.key }}</a>
          <span v-if="L.parent && L.parent.status" class="muted sm">{{ L.parent.status }}</span>
          <span class="lsum">{{ L.parent ? L.parent.summary : $t('board.no_epic') }}</span>
          <small class="muted">{{ $t('board.lane_sum', { total: L.total, word: ticketWord(L.total), pre: L.pre, dev: L.dev, after: L.after }) }}</small></div>
        <div v-if="!store.foldedLanes[L.key]" class="lrow2" :style="{ gridTemplateColumns: gridCols }">
          <div v-for="col in defs" :key="col.id" class="lcell">
            <TicketCard v-for="t in (L.byCol[col.id] || [])" :key="t.k" :t="t" :col="col.id" :checked="!!sel[t.k]" @open="openCard(t, col.id)" @toggle="toggle(t, col.id)" /></div></div>
      </div>
      <div v-if="model.freeAct.length" class="lane"><div class="ltitle">{{ $t('board.lane_free', { n: model.freeAct.length }) }}</div>
        <div class="freerow"><FreeCard v-for="s in model.freeAct" :key="s.session_id" :s="s" /></div></div>
    </div>
    <p class="legendnote">{{ $t('board.legend', { n: model.nTickets, s: model.withSessions, scope: legendScope, filtered: nFilters ? $t('board.legend_filtered') : '' }) }}
      {{ $t('board.legend_cols') }}<span v-if="model.declined"> {{ $t('board.declined', { n: model.declined }) }}</span></p>
    <div v-if="nSel" class="selbar"><b>{{ $t('board.selected', { n: nSel }) }}</b>
      <button v-if="picked.length" class="go" @click="copyAll">{{ $t('board.copy_n', { n: picked.length }) }}</button>
      <span v-else style="color:#94a3b8">{{ $t('board.no_skill') }}</span>
      <button @click="clear">{{ $t('board.cancel') }}</button></div>
    <a-modal :open="!!drawer" :title="null" :footer="null" centered width="880px" wrap-class-name="ticket-modal" @cancel="drawer = null" destroy-on-close>
      <TicketDetail v-if="drawer" :item="drawer" /></a-modal>
  </div>`,
};

export const FreeCard = {
  props: { s: Object },
  setup(props) {
    const open = () => { if (hasAppLink(props.s)) location.href = props.s.app_link; };
    const chip = Vue.computed(() => ({ waiting: "you", suspect: "bad", running: "agent", idle: "idle", closed: "done" })[props.s.state] || "idle");
    return { open, chip, sessionTitle, hasAppLink, ageText, LABEL };
  },
  template: `<div class="card" :class="{ click: hasAppLink(s) }" @click="open">
    <div class="ctop"><b class="csum">{{ sessionTitle(s) }}</b><span class="bd" :class="chip"><i class="dot"></i>{{ LABEL[s.state] }}</span></div>
    <div class="muted sm">{{ s.branch || '—' }} · {{ ageText(s.age_min) }}</div></div>`,
};

export const TicketCard = {
  props: { t: Object, col: String, showParent: Boolean, checked: Boolean },
  emits: ["open", "toggle"],
  setup(props) {
    const j = Vue.computed(() => props.t.j), sess = Vue.computed(() => props.t.sess);
    const act = Vue.computed(() => sess.value.filter(x => x.state !== "closed"));
    const ns = Vue.computed(() => j.value.status ? nextStep(j.value, sess.value) : { text: "" });
    const action = Vue.computed(() => j.value.status ? actionFor(props.t.k, j.value, sess.value, props.col) : null);
    const ball = Vue.computed(() => ballOf(sess.value, props.col));
    const spec = Vue.computed(() => SPEC_COLS.includes(props.col) && j.value.ac && j.value.ac.spec);
    const url = Vue.computed(() => j.value.url && j.value.url.startsWith(store.data.jira_base + "/browse/") ? j.value.url : null);
    const top = Vue.computed(() => sess.value.slice().sort((a, b) => a.age_min - b.age_min).slice(0, 2));
    const copy = async () => { const ok = await copyText(action.value.cmd); antd.message[ok ? "success" : "warning"](ok ? t("board.copied_one", { where: action.value.where || "workspace" }) : t("board.clip_blocked")); };
    return { j, sess, act, ns, action, ball, spec, url, top, copy, tagsOf, GATE_SHORT, GATE_TIP, specLevel, plainSummary, sessionTitle, ageText, STATE_COLOR, LABEL, BALL, BALL_TIP };
  },
  template: `
  <div class="card click" :class="{ dim: sess.length && !act.length, sel: checked }" @click="$emit('open')">
    <div class="ctop">
      <a-checkbox v-if="j.status" :checked="checked" @click.stop @change="$emit('toggle')" />
      <a v-if="url" :href="url" target="_blank" rel="noopener noreferrer" @click.stop><b>{{ t.k }}</b></a><b v-else>{{ t.k }}</b>
      <a-tooltip :title="BALL_TIP[ball]"><span class="bd right" :class="ball"><i class="dot"></i>{{ BALL[ball] }}</span></a-tooltip>
    </div>
    <div v-if="j.summary" class="csum" :title="j.summary">{{ plainSummary(j.summary) }}</div>
    <div class="ctags meta">
      <span v-for="g in tagsOf(j.summary)" :key="g" class="mi">{{ g }}</span>
      <a-tooltip v-if="j.ac && GATE_SHORT[j.ac.gate]" :title="GATE_TIP[j.ac.gate]"><span class="mi">{{ GATE_SHORT[j.ac.gate] }}{{ j.ac.total ? ' ' + j.ac.ticked + '/' + j.ac.total : '' }}</span></a-tooltip>
      <span v-if="['progress', 'release', 'other'].includes(col) && j.status" class="mi">{{ j.status }}</span>
      <span v-if="spec" class="mi" :class="'lv-' + specLevel(spec)">{{ $t('board.spec', { score: spec.score, total: spec.total }) }}</span>
      <a-tooltip v-if="showParent && j.parent" :title="j.parent.summary"><span class="mi">↑ {{ j.parent.key }}</span></a-tooltip>
    </div>
    <div v-if="ns.text" class="cnext" :class="{ hot: ns.hot }">{{ ns.text }}</div>
    <div v-for="s in top" :key="s.session_id" class="csess"><a-badge :status="s.state === 'waiting' ? 'warning' : s.state === 'suspect' ? 'error' : s.state === 'running' ? 'processing' : s.state === 'idle' ? 'success' : 'default'" />
      <span class="t">{{ sessionTitle(s) }}</span><span class="muted sm">{{ ageText(s.age_min) }}</span></div>
    <div v-if="sess.length > 2" class="muted sm">{{ $t('board.more_sessions', { n: sess.length - 2 }) }}</div>
    <div v-if="!sess.length" class="muted sm" :title="$t('board.no_session_tip')">{{ $t('board.no_session') }}</div>
    <div v-if="j.assignee" class="muted sm">{{ j.assignee }}</div>
    <button v-if="action" class="alink cact" :class="{ strong: ball === 'you' }" :title="action.why" @click.stop="copy">⧉ {{ action.cmd }}</button>
  </div>`,
};
