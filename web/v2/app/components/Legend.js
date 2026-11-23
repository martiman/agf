import { STATE_TIP, STATE_COLOR, LABEL, GATE_SHORT, GATE_TIP, INBOX_TYPES, INBOX_CATS, COLS, OTHER_COL, WORKMODE, STATE_ORDER } from "../domain.js";
import { t } from "../i18n.js";
import { store } from "../store.js";

export default {
  setup() {
    const states = STATE_ORDER.filter(k => k !== "unknown").map(k => ({ k, label: LABEL[k], tip: STATE_TIP[k], color: STATE_COLOR[k] }));
    const gates = Object.keys(GATE_SHORT).map(k => ({ k, label: GATE_SHORT[k], tip: GATE_TIP[k] }));
    const wm = Object.entries(WORKMODE).map(([k, v]) => ({ k, label: v }));
    const wmTip = Vue.computed(() => ({ AgentWorking: t("legend.wm.AgentWorking"), WaitingForHuman: t("legend.wm.WaitingForHuman"),
      HumanWorking: t("legend.wm.HumanWorking"), Paused: t("legend.wm.Paused") }));
    const RECC = { delete: "red", archive: "default", review: "orange", keep: "green" };
    return { RECC, store, states, gates, wm, wmTip, INBOX_TYPES, INBOX_CATS, cols: COLS.concat([OTHER_COL]) };
  },
  template: `
  <a-drawer :open="store.legend" :title="$t('legend.title')" width="560" @close="store.legend = false">
    <h4>{{ $t('legend.states') }}</h4>
    <div v-for="s in states" :key="s.k" style="margin-bottom:6px"><a-tag :color="s.color">{{ s.label }}</a-tag> {{ s.tip }}</div>
    <h4 style="margin-top:16px">{{ $t('legend.gates') }}</h4>
    <div v-for="g in gates" :key="g.k" style="margin-bottom:6px"><a-tag>{{ g.label }}</a-tag> {{ g.tip }}</div>
    <h4 style="margin-top:16px">{{ $t('legend.workmode') }}</h4>
    <div v-for="w in wm" :key="w.k" style="margin-bottom:6px"><a-tag>{{ w.label }}</a-tag> {{ wmTip[w.k] }}</div>
    <h4 style="margin-top:16px">{{ $t('legend.inbox') }}</h4>
    <div v-for="c in INBOX_CATS" :key="c.id" style="margin-bottom:8px"><b>{{ c.title }}</b> <span class="muted">{{ c.tip }}</span>
      <div v-for="t in INBOX_TYPES.filter(x => x.cat === c.id)" :key="t.id" style="margin:3px 0 0 12px"><a-tag :color="t.color">{{ t.verb }}</a-tag> {{ t.title }}: {{ t.tip }}</div></div>
    <h4 style="margin-top:16px">{{ $t('legend.cleanup') }}</h4>
    <div v-for="r in ['delete', 'archive', 'review', 'keep']" :key="r" style="margin-bottom:6px"><a-tag :color="RECC[r]">{{ $t('cleanup.rec.' + r) }}</a-tag> {{ $t('legend.cleanup.' + r) }}</div>
    <h4 style="margin-top:16px">{{ $t('legend.board') }}</h4>
    <div v-for="c in cols" :key="c.id" style="margin-bottom:6px"><b>{{ c.title }}</b><span v-if="c.who" class="muted"> · {{ c.who }}</span> – {{ c.tip }}</div>
  </a-drawer>`,
};
