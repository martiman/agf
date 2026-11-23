import { t, srv } from "../i18n.js";

const IC = { ok: "✔", warn: "⚠", fail: "✖", skip: "–", info: "ℹ" };
const COLOR = { ok: "#52c41a", warn: "#faad14", fail: "#ff4d4f", skip: "#8c8c8c", info: "#8c8c8c" };
const RANK = { fail: 0, warn: 1, skip: 2, info: 3, ok: 4 };

export default {
  props: { j: { type: Object, required: true } },
  setup(props) {
    const sp = Vue.computed(() => props.j.ac && props.j.ac.spec);
    const bad = Vue.computed(() => sp.value ? sp.value.checks.filter(c => c.status !== "ok").sort((a, b) => RANK[a.status] - RANK[b.status]) : []);
    const oks = Vue.computed(() => sp.value ? sp.value.checks.filter(c => c.status === "ok") : []);
    const verdict = Vue.computed(() => {
      const s = sp.value; if (!s) return "";
      const w = s.checks.filter(c => c.status === "warn").length;
      return s.block ? t("spec.blocks", { n: s.block }) : w ? t("spec.warns", { n: w }) : t("spec.ready");
    });
    const criteria = Vue.computed(() => (props.j.ac && props.j.ac.criteria) || []);
    const warns = i => { const c = (sp.value && sp.value.criteria[i]) || {}; return (c.warns || []).map((w, n) => srv((c.warns_k || [])[n], w)); };
    return { sp, bad, oks, verdict, criteria, warns, IC, COLOR, srv };
  },
  template: `
  <div>
    <div v-if="sp" class="block">
      <h3>{{ $t('spec.title') }}</h3>
      <div style="font-weight:600">{{ verdict }}</div>
      <div class="muted" style="font-size:12px;margin-bottom:4px">{{ $t('spec.note') }}</div>
      <div v-for="c in bad" :key="c.id" class="chk"><span :style="{ color: COLOR[c.status], fontWeight: 700 }">{{ IC[c.status] }}</span>
        <div><div style="font-weight:600">{{ srv(c.label_k, c.label) }}</div><div v-if="c.detail">{{ srv(c.detail_k, c.detail) }}</div><div v-if="c.hint" class="hint">{{ srv(c.hint_k, c.hint) }}</div></div></div>
      <a-collapse v-if="oks.length" ghost size="small"><a-collapse-panel key="ok" :header="$t('spec.ok_header', { n: oks.length })">
        <div v-for="c in oks" :key="c.id" class="chk"><span :style="{ color: COLOR.ok, fontWeight: 700 }">✔</span><div>{{ srv(c.label_k, c.label) }}</div></div>
      </a-collapse-panel></a-collapse>
    </div>
    <div v-if="criteria.length" class="block">
      <h3>{{ $t('spec.ac_title', { n: j.ac.total }) }}</h3>
      <div v-for="(c, i) in criteria" :key="i" class="acrow">{{ c.ticked ? '☑' : '☐' }} <b v-if="c.id != null">AC-{{ c.id }}:</b> {{ c.text }}
        <div v-for="w in warns(i)" class="w">⚠ {{ w }}</div></div>
    </div>
  </div>`,
};
