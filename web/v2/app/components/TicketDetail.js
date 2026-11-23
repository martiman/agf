import { store, me, tickets, setSnooze } from "../store.js";
import { INBOX_BY_ID, GATE_SHORT, GATE_TIP, WORKMODE, LABEL, nextStep, actionFor, EFFECT, waitText, ageText, specLevel, plainSummary, inboxSession } from "../domain.js";
import { copyText, getDescription } from "../api.js";
import { t, srv } from "../i18n.js";

export default {
  props: { item: { type: Object, required: true } },
  setup(props) {
    const j = Vue.computed(() => props.item.j || {});
    const T = Vue.computed(() => INBOX_BY_ID[props.item.type] || { verb: t("ticket.fallback_verb"), title: j.value.status || t("ticket.fallback_title"), tip: t("ticket.fallback_tip"), color: "default" });
    const key = Vue.computed(() => props.item.key);
    const url = Vue.computed(() => j.value.url && j.value.url.startsWith((store.data.jira_base || "") + "/browse/") ? j.value.url : null);
    const next = Vue.computed(() => key.value && j.value.status ? nextStep(j.value, props.item.sess || []).text : "");
    const wm = Vue.computed(() => j.value.workmode && (j.value.workmode.mode || j.value.workmode.action) ? j.value.workmode : null);
    const sess = Vue.computed(() => (props.item.sess && props.item.sess.length ? props.item.sess : props.item.session ? [props.item.session] : []).slice().sort((a, b) => a.age_min - b.age_min));
    const openSess = Vue.computed(() => { const s = inboxSession(props.item); return s && s.app_link && s.app_link.startsWith("claude://claude.ai/epitaxy/") ? s : null; });
    const approve = Vue.computed(() => store.data.approve || { enabled: true, refined_exists: null });
    const canApprove = Vue.computed(() => ["TO DO", "Backlog"].includes(j.value.status) && j.value.ac && ["draft", "changed"].includes(j.value.ac.gate));
    const approveWhy = Vue.computed(() => !approve.value.enabled ? t("ticket.approve_off")
      : approve.value.refined_exists === false ? t("ticket.no_refined") : "");
    const act = Vue.computed(() => key.value && j.value.status && props.item.colId ? actionFor(key.value, j.value, props.item.sess || [], props.item.colId) : null);
    const acCheck = Vue.computed(() => {
      if (!key.value || !(j.value.ac && j.value.ac.total > 0)) return null;
      const tpl = ((store.data.launch || {}).prompts || {})["ac-check"];
      return { action: "ac-check", key: key.value, where: "", label: t("ticket.accheck_label"), effect: EFFECT["ac-check"],
        cmd: tpl ? tpl.replace("{key}", key.value) : "Proveď nezávislou kontrolu akceptačních kritérií tiketu " + key.value + " (pouze čtení, nic nezapisuj).",
        why: t("ticket.accheck_why") };
    });
    const launchOn = Vue.computed(() => !!(store.data.launch && store.data.launch.enabled));
    const approveOpen = Vue.ref(false), launchAct = Vue.ref(null);
    const copy = async a => { const ok = await copyText(a.cmd); antd.message[ok ? "success" : "warning"](ok ? t("ticket.copied", { where: a.where || "workspace" }) : t("ticket.clip_blocked")); };
    const snooze = v => setSnooze(props.item.id, v === "1h" ? Date.now() + 3600e3 : (() => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(8, 0, 0, 0); return d.getTime(); })());
    const alertType = Vue.computed(() => ["red"].includes(T.value.color) ? "error" : T.value.color === "orange" ? "warning" : "info");
    const label = a => a.label || a.cmd;
    const desc = Vue.reactive({ open: false, loading: false, error: "", data: null });
    const resetDesc = () => Object.assign(desc, { open: false, loading: false, error: "", data: null });
    Vue.watch(key, resetDesc);
    const loadDesc = async refresh => {
      if (!key.value) return;
      const k = key.value; desc.open = true; desc.loading = true; desc.error = "";
      try { const r = await getDescription(k, refresh); if (k !== key.value) return; if (r.error) desc.error = srv(r.error_k, r.error); else desc.data = r; }
      catch (e) { if (k === key.value) desc.error = t("ticket.desc_failed", { error: e.message }); }
      finally { if (k === key.value) desc.loading = false; }
    };
    const toggleDesc = () => { if (desc.open) desc.open = false; else if (desc.data) desc.open = true; else loadDesc(false); };
    const hTag = b => "h" + Math.min(6, Math.max(3, (b.level || 3) + 1));
    return { desc, toggleDesc, loadDesc, hTag, j, T, key, url, next, wm, sess, openSess, canApprove, approveWhy, act, acCheck, launchOn, approveOpen, launchAct, copy, snooze, alertType, label,
             GATE_SHORT, GATE_TIP, WORKMODE, LABEL, waitText, ageText, specLevel, plainSummary };
  },
  template: `
  <div class="dt">
    <div class="dt-key"><a v-if="url" :href="url" target="_blank" rel="noopener noreferrer" :title="$t('ticket.open_in_jira_tip')">{{ key }} ↗</a>
      <span v-else>{{ key || (item.session && item.session.branch) || 'Session' }}</span></div>
    <h1 class="dt-title">{{ j.summary ? plainSummary(j.summary) : (item.session && item.session.title) || '' }}</h1>
    <div class="meta">
      <span v-if="j.status" class="mi"><i class="dot"></i>{{ j.status }}</span>
      <a-tooltip v-if="j.ac && GATE_SHORT[j.ac.gate]" :title="GATE_TIP[j.ac.gate]"><span class="mi">{{ GATE_SHORT[j.ac.gate] }}{{ j.ac.total ? ' ' + j.ac.ticked + '/' + j.ac.total : '' }}</span></a-tooltip>
      <span v-if="j.ac && j.ac.spec" class="mi" :class="'lv-' + specLevel(j.ac.spec)" :title="$t('ticket.spec_tip')">{{ $t('ticket.spec_score', { score: j.ac.spec.score, total: j.ac.spec.total }) }}</span>
      <span v-if="j.type" class="mi">{{ j.type }}</span><span v-if="j.assignee" class="mi">{{ j.assignee }}</span>
    </div>

    <section class="focus" :class="'tone-' + alertType">
      <div class="f-main">
        <div class="f-title">{{ T.verb }}<span v-if="item.sinceMin != null" class="f-since">{{ $t('ticket.since', { t: ageText(item.sinceMin) }) }}</span></div>
        <div class="f-text">{{ T.tip }}</div>
        <div v-if="next" class="f-next">{{ $t('ticket.next') }} <b>{{ next }}</b></div>
        <div v-if="wm" class="f-text">{{ $t('ticket.jira_mode', { mode: WORKMODE[wm.mode] || wm.mode || '—' }) }}<span v-if="wm.action"> – {{ wm.action }}</span></div>
      </div>
      <div class="f-act">
        <a-tooltip v-if="canApprove" :title="approveWhy"><a-button type="primary" :disabled="!!approveWhy" @click="approveOpen = true">{{ $t('ticket.approve_btn') }}</a-button></a-tooltip>
        <a v-else-if="openSess" :href="openSess.app_link"><a-button type="primary">{{ $t('ticket.open_session') }}</a-button></a>
      </div>
    </section>

    <div class="toolbar">
      <a v-if="openSess && canApprove" class="alink" :href="openSess.app_link">{{ $t('ticket.open_session') }}</a>
      <button v-if="key && j.status" class="alink" :aria-expanded="desc.open" @click="toggleDesc" :title="$t('ticket.desc_tip')">{{ desc.open ? $t('ticket.desc_hide') : $t('ticket.desc_show') }}</button>
      <a-dropdown><button class="alink">{{ $t('ticket.snooze') }}</button><template #overlay><a-menu @click="e => snooze(e.key)">
        <a-menu-item key="1h">{{ $t('ticket.snooze_1h') }}</a-menu-item><a-menu-item key="tom">{{ $t('ticket.snooze_tom') }}</a-menu-item></a-menu></template></a-dropdown>
    </div>

    <div v-if="desc.open" class="desc-panel">
      <div class="desc-head"><span class="muted sm">{{ $t('ticket.desc_title') }}</span><span class="desc-tools">
        <button class="alink" :disabled="desc.loading" @click="loadDesc(true)" :title="$t('ticket.refresh_tip')">{{ $t('ticket.refresh') }}</button>
        <a v-if="url" class="alink" :href="url" target="_blank" rel="noopener noreferrer">{{ $t('ticket.open_jira') }}</a>
        <button class="alink" @click="toggleDesc" :aria-label="$t('ticket.hide_aria')">{{ $t('ticket.hide') }}</button></span></div>
      <div class="desc-body" tabindex="0">
        <div v-if="desc.loading && !desc.data" class="muted sm">{{ $t('ticket.loading') }}</div>
        <div v-else-if="desc.error" class="muted sm" style="color:var(--bad)">{{ desc.error }}</div>
        <div v-else-if="desc.data && !desc.data.blocks.length" class="muted sm">{{ $t('ticket.no_desc') }}</div>
        <template v-else-if="desc.data"><template v-for="(b, i) in desc.data.blocks" :key="i">
          <component :is="hTag(b)" v-if="b.k === 'h'" class="d-h"><template v-for="(x, n) in b.text" :key="n">{{ x.t }}</template></component>
          <hr v-else-if="b.k === 'rule'" class="d-hr" />
          <pre v-else-if="b.k === 'code'" class="d-code">{{ b.text[0].t }}</pre>
          <div v-else :class="['d-' + b.k, b.k === 'p' && b.depth ? 'ind' : '']" :style="b.depth ? { marginLeft: (b.depth * 18) + 'px' } : null">
            <span v-if="b.k === 'li'" class="d-mark">{{ b.task ? (b.done ? '☑' : '☐') : b.n ? b.n + '.' : '•' }}</span>
            <span class="d-t"><template v-for="(x, n) in b.text" :key="n"><a v-if="x.href" :href="x.href" target="_blank" rel="noopener noreferrer">{{ x.t }}</a><code v-else-if="x.c">{{ x.t }}</code><b v-else-if="x.b">{{ x.t }}</b><template v-else>{{ x.t }}</template></template></span></div>
        </template>
        <div v-if="desc.data.truncated" class="muted sm">{{ $t('ticket.truncated') }}</div></template>
      </div>
    </div>

    <div v-if="[act, acCheck].some(Boolean)" class="block"><h3>{{ $t('ticket.agent') }}</h3>
      <div v-for="a in [act, acCheck].filter(Boolean)" :key="a.action" class="arow">
        <div class="a-main"><div class="a-name">{{ label(a) }}</div><div class="muted sm">{{ a.why }}</div></div>
        <div class="a-links">
          <a-tooltip :title="$t('ticket.launch_tip')"><button v-if="launchOn" class="alink" @click="launchAct = a">{{ $t('ticket.launch') }}</button></a-tooltip>
          <button class="alink" @click="copy(a)" :title="$t('ticket.copy_tip')">{{ $t('ticket.copy_cmd') }}</button>
        </div>
      </div>
    </div>

    <RefinePanel v-if="key && j.status" :ticket-key="key" :j="j" />

    <div v-if="sess.length" class="block"><h3>{{ $t('ticket.sessions', { n: sess.length }) }}</h3>
      <div v-for="s in sess.slice(0, 6)" :key="s.session_id" class="sess">
        <a-badge :status="s.state === 'waiting' ? 'warning' : s.state === 'suspect' ? 'error' : s.state === 'running' ? 'processing' : s.state === 'idle' ? 'success' : 'default'" />
        <div class="t"><div style="font-weight:600">{{ s.title || s.session_id.slice(0, 8) }}</div>
          <div class="muted" style="font-size:12px">{{ s.branch || '—' }} · {{ LABEL[s.state] || s.state }} · {{ ageText(s.age_min) }}<span v-if="s.notification"> · {{ s.notification }}</span></div></div>
        <a v-if="s.app_link && s.app_link.startsWith('claude://claude.ai/epitaxy/')" class="alink" :href="s.app_link">{{ $t('ticket.open') }}</a>
      </div>
    </div>

    <SpecChecks v-if="j.ac" :j="j" />
    <ApproveModal v-model:open="approveOpen" :ticket-key="key" />
    <LaunchModal :act="launchAct" @close="launchAct = null" />
  </div>`,
};
