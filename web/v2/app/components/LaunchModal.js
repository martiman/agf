import { launchApi } from "../api.js";
import { t, srv } from "../i18n.js";

export default {
  props: { act: Object },
  emits: ["close"],
  setup(props, { emit }) {
    const pre = Vue.ref(null), err = Vue.ref(""), busy = Vue.ref("");
    const where = Vue.ref("");
    const WHERE = Vue.computed(() => [{ value: "", label: t("launch.where_ws") }, { value: "tris", label: t("launch.where_tris") }, { value: "aps_team_git", label: t("launch.where_aps") }]);
    const preview = async () => {
      pre.value = null; err.value = "";
      if (!props.act) return;
      const r = await launchApi(props.act, true, null, where.value);
      if (!r.ok) { err.value = (srv(r.error_k, r.error) || t("launch.err_lc", { status: r.status })) + (r.hint ? " (" + srv(r.hint_k, r.hint) + ")" : ""); return; }
      pre.value = r;
    };
    Vue.watch(() => props.act, a => { if (a) where.value = a.where || ""; preview(); });
    Vue.watch(where, () => { if (props.act) preview(); });
    const go = async method => {
      busy.value = method;
      const r = await launchApi(props.act, false, method, where.value);
      busy.value = "";
      if (r.ok) { antd.message.success(r.method === "terminal" ? t("launch.ok_terminal") : t("launch.ok_app")); emit("close"); }
      else err.value = srv(r.error_k, r.error) || t("launch.err", { status: r.status });
    };
    return { pre, err, busy, go, emit, where, WHERE };
  },
  template: `
  <a-modal :open="!!act" :title="act ? $t('launch.title', { key: act.key }) : ''" @cancel="emit('close')" :footer="null" destroy-on-close>
    <a-alert v-if="err" type="error" show-icon :message="err" style="margin-bottom:10px" />
    <div style="margin-bottom:8px"><b>{{ $t('launch.project') }}</b>
      <a-select v-model:value="where" :options="WHERE" style="width:100%;margin-top:4px" :disabled="!!busy" /></div>
    <div v-if="pre">
      <p><b>{{ $t('launch.folder') }}</b> {{ pre.folder }}</p>
      <div class="muted">{{ $t('launch.prompt') }}</div><pre class="prompt">{{ pre.prompt }}</pre>
      <p class="muted">{{ $t('launch.after', { effect: act.effect }) }}</p>
      <ul class="muted"><li><b>{{ $t('launch.in_app') }}</b>: {{ $t('launch.in_app_text') }}</li>
        <li><b>{{ $t('launch.in_terminal') }}</b>: {{ $t('launch.in_terminal_text') }}</li></ul>
      <a-space><a-button @click="emit('close')">{{ $t('launch.cancel') }}</a-button>
        <a-button type="primary" :loading="busy === 'app'" :disabled="!!busy" @click="go('app')">{{ $t('launch.open_app') }}</a-button>
        <a-button danger :loading="busy === 'terminal'" :disabled="!!busy" @click="go('terminal')">{{ $t('launch.run_terminal') }}</a-button></a-space>
    </div>
  </a-modal>`,
};
