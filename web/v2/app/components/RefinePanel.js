import { t, locale, srv } from "../i18n.js";
import { getJSON, refineApi, copyText } from "../api.js";
import { store } from "../store.js";

export default {
  props: { ticketKey: String, j: Object },
  setup(props) {
    const CONT = "pokračuj", SECTION = "Otevřené otázky";
    const ACCEPT = "Přijmout návrh: ";
    const rec = Vue.ref(null), forms = Vue.reactive({}), busy = Vue.ref(false), checks = Vue.ref([]), edits = Vue.reactive({});
    const summary = Vue.computed(() => (store.data && store.data.refine && store.data.refine[props.ticketKey]) || null);
    const load = async () => {
      if (!summary.value) { rec.value = null; return; }
      try { const r = await getJSON("/api/refine?key=" + props.ticketKey); rec.value = r.record; checks.value = r.checks || []; } catch (e) {  }
    };
    Vue.watch(() => [props.ticketKey, summary.value && summary.value.updated_at], load, { immediate: true });

    const jiraNew = Vue.computed(() => {
      const qs = (props.j && props.j.ac && props.j.ac.spec && props.j.ac.spec.questions) || [];
      const have = new Set(((rec.value && rec.value.questions) || []).map(q => q.src_text));
      return qs.filter(x => !have.has(x));
    });
    const pending = Vue.computed(() => ((rec.value && rec.value.questions) || []).filter(q => !q.answer));
    const toPost = Vue.computed(() => ((rec.value && rec.value.questions) || []).filter(q => q.answer && !q.answer.defer && !q.posted_at));
    const form = q => (forms[q.id] ||= { choice: null, text: "", defer: false });
    const answered = q => { const f = forms[q.id]; return !!f && (f.choice || f.text.trim() || f.defer); };
    const nAnswered = Vue.computed(() => pending.value.filter(answered).length);
    const answerText = a => a.defer ? t("refine.deferred") : [a.choice, a.text].filter(Boolean).join(" · ");
    const fmt = iso => iso ? new Date(iso).toLocaleString(locale()) : "?";

    const call = async (action, body, ok) => {
      busy.value = true;
      const r = await refineApi(action, Object.assign({ key: props.ticketKey }, body));
      busy.value = false;
      if (!r.ok) { antd.message.error(srv(r.error_k, r.error) || t("refine.error", { status: r.status })); return null; }
      if (r.record) rec.value = r.record;
      if (r.checks) checks.value = r.checks;
      ok && ok(r);
      return r;
    };
    const doImport = () => call("import", {}, r => antd.message.success(r.imported ? t("refine.imported", { n: r.imported }) : t("refine.nothing_new")));
    const send = () => {
      const answers = {};
      pending.value.forEach(q => { if (answered(q)) { const f = forms[q.id]; answers[q.id] = { choice: f.choice, text: f.text.trim(), defer: f.defer }; } });
      call("answer", { answers }, () => { Object.keys(answers).forEach(id => delete forms[id]); antd.message.success(t("refine.saved")); });
    };
    const post = () => antd.Modal.confirm({
      title: t("refine.post_title", { key: props.ticketKey }), okText: t("refine.post_ok"), cancelText: t("refine.cancel"), width: 560,
      content: Vue.h("div", [toPost.value.map(q => Vue.h("p", { style: "margin:0 0 6px" }, "• " + q.text + " → " + answerText(q.answer))),
        Vue.h("p", { class: "muted" }, t("refine.desc_unchanged"))]),
      onOk: () => call("post-decision", {}, r => antd.message.success(t("refine.posted", { first: r.first }) + (r.still_in_description
        ? " " + t("refine.still_in_desc", { section: SECTION }) : ""), 8)),
    });
    const norm = x => String(x || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
    const draft = Vue.computed(() => rec.value && rec.value.draft && ["draft", "approved", "written"].includes(rec.value.stage) ? rec.value.draft : null);
    const editable = Vue.computed(() => !!rec.value && rec.value.stage === "draft");
    const jiraAc = Vue.computed(() => ((props.j && props.j.ac && props.j.ac.criteria) || []).filter(c => c.id != null));
    const acState = a => { const old = jiraAc.value.find(c => c.id === a.id); return !old ? "new" : norm(old.text) !== norm(a.text) ? "changed" : "same"; };
    const removed = Vue.computed(() => draft.value ? jiraAc.value.filter(c => !draft.value.ac.some(a => a.id === c.id)) : []);
    const val = a => edits[a.id] != null ? edits[a.id] : a.text;
    const approveDraft = async () => {
      const changed = {};
      draft.value.ac.forEach(a => { const v = edits[a.id]; if (v != null && v.trim() && v.trim() !== a.text) changed[a.id] = v; });
      busy.value = true;
      if (Object.keys(changed).length) {
        const e = await refineApi("edit", { key: props.ticketKey, ac: changed });
        if (!e.ok) { busy.value = false; antd.message.error(t("refine.edit_failed", { error: srv(e.error_k, e.error) || t("refine.error", { status: e.status }) })); return; }
      }
      busy.value = false;
      await call("approve-draft", {}, () => { Object.keys(edits).forEach(k => delete edits[k]); antd.message.success(t("refine.approved", { cmd: CONT })); });
    };
    const cont = async () => { const ok = await copyText(CONT); antd.message[ok ? "success" : "warning"](ok ? t("refine.copied", { cmd: CONT }) : t("refine.clip_blocked")); };
    return { srv, summary, rec, checks, edits, draft, editable, acState, removed, val, approveDraft, jiraNew, pending, toPost, form, answered, nAnswered, answerText, fmt, busy, doImport, send, post, cont, CONT, ACCEPT };
  },
  template: `
  <div v-if="rec || jiraNew.length || (summary && summary.stage === 'draft')" class="block">
    <h3>{{ $t('refine.title') }}</h3>
    <div v-if="jiraNew.length" class="note warn">{{ $t('refine.jira_new', { n: jiraNew.length }) }}
      <button class="alink" :disabled="busy" @click="doImport">{{ $t('refine.import') }}</button></div>
    <div v-if="summary && summary.stage === 'draft'" class="note warn">{{ $t('refine.draft_waits', { version: draft ? draft.version : '' }) }}</div>
    <div v-if="summary && summary.waiting_agent" class="note">{{ $t('refine.agent_unaware', { cmd: CONT }) }}
      <button class="alink" @click="cont">{{ $t('refine.copy_cmd', { cmd: CONT }) }}</button></div>
    <template v-if="rec">
      <div v-for="q in rec.questions" :key="q.id" class="q">
        <div class="qt">{{ q.id }} · {{ q.text }}</div><div v-if="q.why" class="qw">{{ q.why }}</div>
        <template v-if="q.answer">
          <a-tag :color="q.answer.defer ? 'default' : 'green'">{{ answerText(q.answer) }}</a-tag>
          <div v-if="q.posted_at" class="muted" style="font-size:12px">{{ $t('refine.posted_as', { as: q.posted_as, date: fmt(q.posted_at) }) }}</div>
          <div v-else-if="q.source === 'jira'" class="muted" style="font-size:12px">{{ $t('refine.from_jira') }}</div>
        </template>
        <template v-else>
          <a-radio-group v-if="q.options.length" :value="form(q).choice" @change="e => { form(q).choice = e.target.value; form(q).defer = false; }" style="display:flex;flex-direction:column;gap:4px;margin-bottom:6px">
            <a-radio v-for="o in q.options" :key="o.label" :value="o.label"><span>{{ o.label }}</span> <a-tag v-if="o.recommended" color="green">{{ $t('refine.recommended') }}</a-tag>
              <div v-if="o.note && o.note !== o.label.replace(ACCEPT, '')" class="muted" style="font-size:12px;white-space:normal">{{ o.note }}</div></a-radio>
          </a-radio-group>
          <a-textarea v-model:value="form(q).text" :rows="2" :maxlength="1000" :placeholder="q.options.length ? $t('refine.other_answer') : $t('refine.your_answer')" />
          <a-checkbox v-model:checked="form(q).defer" style="margin-top:6px">{{ $t('refine.decide_later') }}</a-checkbox>
        </template>
      </div>
      <a-space v-if="pending.length"><a-button type="primary" :disabled="!nAnswered" :loading="busy" @click="send">{{ $t('refine.send', { a: nAnswered, n: pending.length }) }}</a-button></a-space>
      <a-button v-if="toPost.length" :loading="busy" @click="post">{{ $t('refine.post', { n: toPost.length }) }}</a-button>
      <div v-if="draft" class="block">
        <h3>{{ $t('refine.draft_title', { version: draft.version }) }}</h3>
        <div v-for="[t, v] in [[$t('refine.problem'), draft.problem], [$t('refine.where'), draft.where], [$t('refine.expected'), draft.expected]]" :key="t" style="margin-bottom:8px">
          <div style="font-weight:600">{{ t }}</div><div style="white-space:pre-wrap">{{ v || $t('refine.empty') }}</div></div>
        <div style="font-weight:600">{{ $t('refine.ac', { n: draft.ac.length }) }}</div>
        <div v-for="a in draft.ac" :key="a.id" class="acrow">
          <b>AC-{{ a.id }}</b>
          <a-input v-if="editable" :value="val(a)" :maxlength="1500" @update:value="v => edits[a.id] = v" style="margin:2px 0" />
          <div v-else>{{ a.text }}</div>
          <div class="muted" style="font-size:12px"><span v-if="a.from">{{ $t('refine.from', { from: a.from }) }}</span><a-tag v-if="a.edited" color="blue">{{ $t('refine.edited') }}</a-tag>
            <a-tag :color="acState(a) === 'new' ? 'green' : acState(a) === 'changed' ? 'orange' : 'default'">{{ $t('refine.ac_' + acState(a)) }}</a-tag></div></div>
        <div v-for="c in removed" :key="c.id" class="acrow"><b>AC-{{ c.id }}</b> <s>{{ c.text }}</s> <a-tag color="red">{{ $t('refine.removed') }}</a-tag></div>
        <div v-if="draft.decisions.length" style="margin-top:8px"><div style="font-weight:600">{{ $t('refine.decisions') }}</div>
          <div v-for="x in draft.decisions" class="muted">{{ (x.q ? x.q + ' · ' : '') + (x.text ? x.text + ' → ' : '') + x.choice + (x.note ? ' (' + x.note + ')' : '') }}</div></div>
        <div v-if="draft.unresolved.length" style="margin-top:8px"><div style="font-weight:600">{{ $t('refine.unresolved') }}</div>
          <div v-for="u in draft.unresolved" style="color:#d48806">⚠ {{ u }}</div></div>
        <div v-if="checks.length" style="margin-top:8px"><div style="font-weight:600">{{ $t('refine.checks') }}</div>
          <div v-for="c in checks" :style="{ color: c.status === 'ok' ? '#389e0d' : '#d48806' }">{{ c.status === 'ok' ? '✔' : '⚠' }} {{ srv(c.label_k, c.label) }}<span v-if="c.detail">: {{ srv(c.detail_k, c.detail) }}</span></div></div>
        <a-button v-if="editable" type="primary" :loading="busy" style="margin-top:10px" @click="approveDraft"
          :title="$t('refine.approve_tip', { cmd: CONT })">{{ $t('refine.approve', { version: draft.version }) }}</a-button>
        <div v-else-if="rec.stage === 'approved'" class="note ok">{{ $t('refine.approved_note', { version: rec.approved_version }) }}</div>
        <div v-else-if="rec.stage === 'written'" class="note ok">{{ $t('refine.written') }}</div>
      </div>
    </template>
  </div>
  <div v-else class="note">{{ $t('refine.empty_dialog') }}</div>`,
};
