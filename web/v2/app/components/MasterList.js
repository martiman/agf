import { store, shownItems, openItems, snoozedItems, urgent, selected, select, clearSnooze } from "../store.js";
import { t } from "../i18n.js";
import { INBOX_CATS, INBOX_BY_ID, catOf, ageText, plainSummary, specLevel, GATE_SHORT, GATE_TIP, BALL, BALL_TIP } from "../domain.js";

export default {
  props: { narrow: Boolean },
  setup() {
    const groups = Vue.computed(() => INBOX_CATS.map(c => ({ ...c, items: shownItems.value.filter(i => catOf(i) === c) })).filter(g => g.items.length));
    const folded = g => g.folded && !store.q && store.foldedCats[g.id];
    const toggle = g => { if (g.folded) store.foldedCats[g.id] = !store.foldedCats[g.id]; };
    const T = it => INBOX_BY_ID[it.type];
    const ball = it => catOf(it).id === "others" ? "other" : "you";
    const sum = it => (it.j && it.j.summary) ? plainSummary(it.j.summary) : (it.session && it.session.title) || "";
    const name = it => it.key || (it.session && (it.session.branch || "session")) || "—";
    const showGate = it => it.j && it.j.ac && GATE_SHORT[it.j.ac.gate] && ["ac-review", "ac-missing", "agent-asks", "refined", "refine-questions", "refine-draft", "refine-continue"].includes(it.type);
    const spec = it => it.j && it.j.ac && it.j.ac.spec && ["ac-review", "ac-missing", "refined"].includes(it.type) ? it.j.ac.spec : null;
    const humanWm = it => it.j && it.j.workmode && ["HumanWorking", "Paused"].includes(it.j.workmode.mode) ? it.j.workmode.mode : null;
    const head = Vue.computed(() => urgent.value ? t("master.head_urgent", { n: urgent.value }) : openItems.value.length ? t("master.head_none") : t("master.head_empty"));
    return { store, groups, folded, toggle, T, ball, sum, name, showGate, spec, humanWm, selected, select, openItems, snoozedItems, clearSnooze, head,
             ageText, specLevel, GATE_SHORT, GATE_TIP, BALL, BALL_TIP };
  },
  template: `
  <div class="master" :class="{ full: narrow }">
    <div class="phead">
      <div class="prow"><h2>Inbox</h2><span class="muted">{{ head }}</span></div>
      <a-input-search v-model:value="store.q" :placeholder="$t('master.search')" allow-clear size="small" />
    </div>
    <div v-if="!openItems.length" class="emptybox"><div class="ok">✔</div><b>{{ $t('master.head_empty') }}</b>
      <span>{{ $t('master.empty_hint') }}</span>
      <button class="alink" @click="store.view = 'list'">{{ $t('master.go_sessions') }}</button></div>
    <div v-else-if="!groups.length" class="empty">{{ $t('master.no_match') }}</div>
    <template v-for="g in groups" :key="g.id">
      <a-tooltip :title="g.tip"><div class="ghead" :class="{ click: g.folded }" @click="toggle(g)">
        <span class="gdot" :class="{ danger: g.danger, warn: g.warn }"></span><span v-if="g.folded">{{ folded(g) ? '▸' : '▾' }}</span><span>{{ g.title }}</span><small>{{ g.items.length }}</small></div></a-tooltip>
      <template v-if="!folded(g)">
        <div v-for="it in g.items" :key="it.id" class="lrow" :class="{ sel: selected && selected.id === it.id }" @click="select(it)">
          <div class="ltop"><b>{{ name(it) }}</b><span class="ls" :title="it.j && it.j.summary">{{ sum(it) }}</span><span class="muted sm">{{ ageText(it.sinceMin) }}</span></div>
          <div class="lbot meta">
            <a-tooltip :title="BALL_TIP[ball(it)]"><span class="mi bd" :class="ball(it)"><i class="dot"></i>{{ BALL[ball(it)] }}</span></a-tooltip>
            <a-tooltip :title="T(it).tip"><span class="mi">{{ T(it).verb }}</span></a-tooltip>
            <a-tooltip v-if="showGate(it)" :title="GATE_TIP[it.j.ac.gate]"><span class="mi">{{ GATE_SHORT[it.j.ac.gate] }}{{ it.j.ac.total ? ' ' + it.j.ac.ticked + '/' + it.j.ac.total : '' }}</span></a-tooltip>
            <span v-if="spec(it)" class="mi" :class="'lv-' + specLevel(spec(it))">{{ $t('master.spec', { score: spec(it).score, total: spec(it).total }) }}</span>
            <span v-if="humanWm(it)" class="mi">{{ humanWm(it) === 'Paused' ? $t('master.paused') : $t('master.human') }}</span>
          </div>
        </div>
      </template>
    </template>
    <div v-if="snoozedItems.length" style="padding:12px 16px">
      <button class="alink" @click="store.showSnoozed = !store.showSnoozed">{{ store.showSnoozed ? $t('master.hide_snoozed') : $t('master.snoozed', { n: snoozedItems.length }) }}</button>
      <div v-if="store.showSnoozed" style="margin-top:8px">
        <div v-for="it in snoozedItems" :key="it.id" class="lrow dim" @click="select(it)">
          <div class="ltop"><b>{{ name(it) }}</b><span class="ls">{{ sum(it) }}</span><button class="alink" @click.stop="clearSnooze(it.id)">{{ $t('master.return') }}</button></div>
        </div>
      </div>
    </div>
  </div>`,
};
