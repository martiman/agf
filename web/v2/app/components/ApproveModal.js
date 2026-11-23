import { approveApi } from "../api.js";
import { refresh } from "../store.js";
import { t, srv } from "../i18n.js";

export default {
  props: { open: Boolean, ticketKey: String },
  emits: ["update:open"],
  setup(props, { emit }) {
    const plan = Vue.ref(null), loading = Vue.ref(false), consent = Vue.ref(false), reason = Vue.ref(""), err = Vue.ref(""), stale = Vue.ref(false);
    const load = async () => {
      plan.value = null; err.value = ""; stale.value = false; consent.value = false; reason.value = "";
      loading.value = true;
      const r = await approveApi({ key: props.ticketKey, dry: true });
      loading.value = false;
      if (!r.ok) { err.value = (srv(r.error_k, r.error) || t("approve.err_lc", { status: r.status })) + (r.hint ? " (" + srv(r.hint_k, r.hint) + ")" : ""); return; }
      plan.value = r.plan;
    };
    Vue.watch(() => props.open, o => { if (o) load(); });
    const canGo = Vue.computed(() => plan.value && consent.value && (!plan.value.requires_reason || reason.value.trim().length >= 10) && !stale.value);
    const missing = Vue.computed(() => {
      if (!plan.value) return "";
      if (stale.value) return t("approve.stale");
      const m = [];
      if (plan.value.requires_reason && reason.value.trim().length < 10) m.push(t("approve.need_reason", { n: 10 - reason.value.trim().length }));
      if (!consent.value) m.push(t("approve.need_consent"));
      return m.length ? t("approve.missing", { list: m.join(t("approve.and")) }) : "";
    });
    const go = async () => {
      loading.value = true; err.value = "";
      const r = await approveApi({ key: props.ticketKey, fingerprint: plan.value.fingerprint, confirm: true, reason: reason.value.trim() });
      loading.value = false;
      if (r.ok) {
        antd.message.success(t(r.comment === false ? "approve.done_nocomment" : "approve.done", { key: props.ticketKey, to: r.to }));
        emit("update:open", false); refresh(true); return;
      }
      err.value = srv(r.error_k, r.error) || t("approve.err", { status: r.status });
      if (r.status === 409) stale.value = true;
    };
    const warnList = Vue.computed(() => plan.value ? plan.value.warns.map((w, i) => srv((plan.value.warns_k || [])[i], w)).join("; ") : "");
    return { plan, loading, consent, reason, err, stale, canGo, missing, go, load, emit, srv, warnList };
  },
  template: `
  <a-modal :open="open" :title="$t('approve.title', { key: ticketKey })" width="720px" @cancel="emit('update:open', false)" :footer="null" destroy-on-close>
    <a-spin :spinning="loading">
      <a-alert v-if="err" type="error" show-icon :message="err" style="margin-bottom:10px" />
      <a-button v-if="stale" style="margin-bottom:10px" @click="load">{{ $t('approve.reload') }}</a-button>
      <div v-if="plan">
        <p><b>{{ $t('approve.l_ticket') }}</b> {{ plan.summary }}<br><b>{{ $t('approve.l_transition') }}</b> {{ $t('approve.transition', { status: plan.status, to: plan.transition.to, name: plan.transition.name }) }}<br>
          <b>{{ $t('approve.l_spec') }}</b> {{ plan.score }}/{{ plan.total }}<span v-if="plan.warns.length">{{ $t('approve.warns', { list: warnList }) }}</span></p>
        <a-alert v-if="!plan.requires_reason" type="success" show-icon :message="$t('approve.ok_msg')" style="margin-bottom:10px" />
        <h4>{{ $t('approve.criteria', { n: plan.criteria.length }) }}</h4>
        <div style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:4px 10px">
          <div v-for="c in plan.criteria" class="acrow"><b v-if="c.id != null">AC-{{ c.id }}:</b> {{ c.text }}</div></div>
        <div v-if="plan.requires_reason" style="margin-top:10px">
          <a-alert type="warning" show-icon :message="$t('approve.warn_msg')">
            <template #description><ul style="margin:4px 0 0 16px"><li v-for="b in plan.blocks">{{ srv(b.label_k, b.label) }}<span v-if="b.detail"> ({{ srv(b.detail_k, b.detail) }})</span></li></ul></template>
          </a-alert>
          <div style="margin:6px 0 4px"><b>{{ $t('approve.reason_title') }}</b> <span class="muted">{{ $t('approve.reason_help') }}</span></div>
          <a-textarea v-model:value="reason" :rows="2" :maxlength="500" :placeholder="$t('approve.reason_ph')" />
        </div>
        <a-checkbox v-model:checked="consent" style="margin-top:12px">{{ $t('approve.consent') }}</a-checkbox>
        <div class="muted" style="font-size:12px;margin:6px 0 12px">{{ $t('approve.after') }}</div>
        <div v-if="missing" style="color:#d46b08;margin-bottom:8px">{{ missing }}</div>
        <a-space><a-button @click="emit('update:open', false)">{{ $t('approve.cancel') }}</a-button>
          <a-button type="primary" :disabled="!canGo" :loading="loading" @click="go">{{ plan.requires_reason ? $t('approve.btn_anyway') : $t('approve.btn') }}</a-button></a-space>
      </div>
    </a-spin>
  </a-modal>`,
};
