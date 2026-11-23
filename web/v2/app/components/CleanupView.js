import { store, loadIdeas } from "../store.js";
import { ageText } from "../domain.js";
import { getJSON, post, ideasApi } from "../api.js";
import { t, srv } from "../i18n.js";

export default {
  setup() {
    const rows = Vue.ref([]), loading = Vue.ref(false), err = Vue.ref("");
    const q = Vue.ref(""), minDays = Vue.ref(0), recF = Vue.ref("*"), repo = Vue.ref("*"), showArchived = Vue.ref(false);
    const sel = Vue.reactive({}), busy = Vue.ref(false);
    const AGES = Vue.computed(() => [{ value: 0, label: t("cleanup.age.any") }, ...[7, 14, 30, 60].map(n => ({ value: n, label: t("cleanup.age.older", { n }) }))]);
    const repoOf = s => (s.cwd || "").split("/").pop() || "—";
    const load = async () => {
      loading.value = true; err.value = "";
      try { rows.value = (await getJSON("/api/app-sessions")).sessions; }
      catch (e) { err.value = t("cleanup.load_failed", { error: e.message }); }
      finally { loading.value = false; }
    };
    const repos = Vue.computed(() => [{ value: "*", label: t("cleanup.repo.all") }, ...[...new Set(rows.value.map(repoOf))].sort().map(r => ({ value: r, label: r }))]);
    const shown = Vue.computed(() => {
      const needle = q.value.trim().toLowerCase();
      return rows.value.filter(s => s.archived === showArchived.value
        && (repo.value === "*" || repoOf(s) === repo.value)
        && (showArchived.value || recF.value === "*" || (s.rec && s.rec.action === recF.value))
        && (showArchived.value || (s.age_min == null ? true : s.age_min >= minDays.value * 1440))
        && (!needle || ((s.title || "") + " " + s.cwd).toLowerCase().includes(needle)))
        .sort((a, b) => (a.last || 0) - (b.last || 0));
    });
    const pickable = Vue.computed(() => shown.value.filter(s => showArchived.value || !s.busy));
    const picked = Vue.computed(() => pickable.value.filter(s => sel[s.id]));
    const allOn = Vue.computed(() => pickable.value.length > 0 && picked.value.length === pickable.value.length);
    const toggleAll = () => { const on = !allOn.value; pickable.value.forEach(s => { sel[s.id] = on; }); };
    Vue.watch([q, minDays, repo, showArchived, recF], () => Object.keys(sel).forEach(k => delete sel[k]));
    const run = async (action, list) => {
      busy.value = true;
      const r = await post("/api/app-sessions", { action, ids: list.map(s => s.id) });
      busy.value = false;
      if (!r.ok) { antd.message.error(srv(r.error_k, r.error) || t("cleanup.err_status", { status: r.status })); return; }
      Object.keys(sel).forEach(k => delete sel[k]);
      const n = r.done.length;
      if (n) antd.message.success(t((action === "archive" ? "cleanup.done.archived" : "cleanup.done.restored") + (r.skipped.length ? "_skipped" : ""), { n, skipped: r.skipped.length, why: r.skipped.length ? srv(r.skipped[0].why_k, r.skipped[0].why) : "" }));
      else antd.message.warning(t("cleanup.nothing_changed", { why: r.skipped[0] ? srv(r.skipped[0].why_k, r.skipped[0].why) : "" }));
      await load();
    };
    const archive = () => {
      const list = picked.value;
      antd.Modal.confirm({
        title: t("cleanup.archive.title", { n: list.length }),
        content: t("cleanup.archive.body"),
        okText: t("cleanup.archive.ok"), cancelText: t("ant.cancel"), onOk: () => run("archive", list),
      });
    };
    const srcOf = s => ({ session_id: s.id, title: s.title || "", cwd: s.cwd || "", ticket: s.ticket || "", last: s.last || null });
    const ideaText = s => ((s.title ? s.title + ": " : "") + (s.first_prompt || "")).trim();
    const idea = Vue.reactive({ open: false, s: null, text: "", busy: false });
    const askIdea = s => Object.assign(idea, { open: true, s, text: ideaText(s), busy: false });
    const saveIdea = async () => {
      idea.busy = true;
      const r = await ideasApi({ action: "add", text: idea.text, context: idea.s.last_reply || "", source: srcOf(idea.s), dedupe: false });
      idea.busy = false;
      if (!r.ok) { antd.message.error(srv(r.error_k, r.error) || t("cleanup.err_status", { status: r.status })); return; }
      idea.open = false; antd.message.success(t("cleanup.idea.saved")); loadIdeas();
    };
    const restore = () => run("restore", picked.value);
    const del = Vue.reactive({ open: false, list: [], bytes: 0, text: "", busy: false, err: "", keep: true });
    const mb = b => b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " kB";
    const rescuable = Vue.computed(() => del.list.filter(s => s.first_prompt));
    const askDelete = async () => {
      const list = picked.value.slice();
      const r = await post("/api/app-sessions", { action: "delete", ids: list.map(s => s.id), dry: true });
      if (!r.ok) { antd.message.error(srv(r.error_k, r.error) || t("cleanup.err_status", { status: r.status })); return; }
      Object.assign(del, { open: true, list: list.filter(s => r.done.includes(s.id)), bytes: r.bytes, text: "", keep: true, err: r.skipped.length ? t("cleanup.del.skipped", { n: r.skipped.length, why: srv(r.skipped[0].why_k, r.skipped[0].why) }) : "" });
      if (!del.list.length) { del.open = false; antd.message.warning(t("cleanup.del.nothing", { why: r.skipped[0] ? srv(r.skipped[0].why_k, r.skipped[0].why) : "" })); }
    };
    const doDelete = async () => {
      del.busy = true; del.err = "";
      if (del.keep && rescuable.value.length) {
        const items = rescuable.value.map(s => ({ text: ideaText(s), context: s.last_reply || "", source: srcOf(s) }));
        const k = await ideasApi({ action: "add_many", items });
        if (!k.ok) { del.busy = false; del.err = t("cleanup.del.ideas_failed", { error: srv(k.error_k, k.error) || k.status }); return; }
      }
      const r = await post("/api/app-sessions", { action: "delete", ids: del.list.map(s => s.id) });
      del.busy = false;
      if (!r.ok) { del.err = srv(r.error_k, r.error) || t("cleanup.err_status", { status: r.status }); return; }
      del.open = false; Object.keys(sel).forEach(k => delete sel[k]); loadIdeas();
      antd.message.success(t(r.skipped.length ? "cleanup.del.done_skipped" : "cleanup.del.done", { n: r.done.length, size: mb(r.bytes), skipped: r.skipped.length }));
      await load();
    };
    const REC = Vue.computed(() => ({ delete: [t("cleanup.rec.delete"), "bad"], archive: [t("cleanup.rec.archive"), "idle"], review: [t("cleanup.rec.review"), "you"], keep: [t("cleanup.rec.keep"), "done"] }));
    const confirmWord = Vue.computed(() => t("cleanup.del.word"));
    const recCount = Vue.computed(() => { const c = {}; rows.value.filter(s => !s.archived).forEach(s => { const a = s.rec ? s.rec.action : "keep"; c[a] = (c[a] || 0) + 1; }); return c; });
    const nOld = Vue.computed(() => rows.value.filter(s => !s.archived && !s.in_agf).length);
    const nActive = Vue.computed(() => rows.value.filter(s => !s.archived).length);
    const nArch = Vue.computed(() => rows.value.filter(s => s.archived).length);
    Vue.watch(() => store.view, v => { if (v === "cleanup") load(); }, { immediate: true });
    return { srv, confirmWord, idea, askIdea, saveIdea, rescuable, REC, recCount, recF, del, mb, askDelete, doDelete, rows, loading, err, q, minDays, repo, showArchived, sel, busy, AGES, repos, shown, pickable, picked, allOn, toggleAll, archive, restore, load, repoOf, ageText, nOld, nActive, nArch };
  },
  template: `
  <div class="scroll">
    <div class="phead">
      <div class="prow bfilters">
        <h2>{{ $t('nav.cleanup') }}</h2>
        <a-input-search v-model:value="q" :placeholder="$t('cleanup.search')" allow-clear size="small" style="width:240px" />
        <a-select v-if="!showArchived" size="small" v-model:value="minDays" :options="AGES" style="width:170px" />
        <a-select size="small" v-model:value="repo" :options="repos" style="width:170px" />
        <a-checkbox v-model:checked="showArchived">{{ $t('cleanup.show_archived', { n: nArch }) }}</a-checkbox>
        <span class="muted sm" style="margin-left:auto">{{ $t('cleanup.counts', { active: nActive, old: nOld }) }}</span>
        <button class="alink" :disabled="loading" @click="load">{{ $t('shell.refresh') }}</button>
      </div>
    </div>
    <div v-if="!showArchived" class="strip rec-strip">
      <button v-for="k in ['delete', 'archive', 'review', 'keep']" :key="k" class="tile" :class="[REC[k][1], { on: recF === k }]" @click="recF = recF === k ? '*' : k">
        <span><b>{{ recCount[k] || 0 }}</b> {{ REC[k][0] }}</span></button>
      <span class="muted sm rec-note">{{ $t('cleanup.rec_note') }}</span>
    </div>
    <div v-if="err" class="empty">{{ err }}</div>
    <div v-else-if="loading && !rows.length" class="empty">{{ $t('cleanup.loading') }}</div>
    <div v-else-if="!shown.length" class="empty">{{ $t(showArchived ? 'cleanup.empty.archived' : 'cleanup.empty.filter') }}</div>
    <div v-else class="stable">
      <div class="crow head"><span><a-checkbox :checked="allOn" :indeterminate="picked.length > 0 && !allOn" @change="toggleAll" /></span><span>{{ $t('cleanup.col.session') }}</span><span>{{ $t('cleanup.col.rec') }}</span><span>{{ $t('cleanup.col.folder') }}</span><span class="n">{{ $t('cleanup.col.turns') }}</span><span>{{ $t('cleanup.col.last') }}</span><span></span></div>
      <div v-for="s in shown" :key="s.id" class="crow" :class="{ off: !showArchived && s.busy }" @click="!(!showArchived && s.busy) && (sel[s.id] = !sel[s.id])">
        <span @click.stop><a-tooltip :title="!showArchived && s.busy ? $t('cleanup.busy_tip') : ''"><a-checkbox v-model:checked="sel[s.id]" :disabled="!showArchived && s.busy" /></a-tooltip></span>
        <span style="min-width:0"><div class="st">{{ s.title || $t('cleanup.untitled') }}</div>
          <div v-if="s.first_prompt" class="sum" :title="s.first_prompt"><i>{{ $t('cleanup.started') }}</i> {{ s.first_prompt }}</div>
          <div v-if="s.last_reply" class="sum" :title="s.last_reply"><i>{{ $t('cleanup.ended') }}</i> {{ s.last_reply }}</div>
          <div v-if="!s.first_prompt && !s.last_reply" class="sum">{{ $t('cleanup.no_transcript') }}</div>
          <div class="sub muted">{{ s.ticket ? s.ticket + (s.ticket_status ? ' · ' + s.ticket_status + ' · ' : ' · ') : '' }}{{ $t(s.in_agf ? 'cleanup.in_agf' : 'cleanup.app_only') }}</div></span>
        <span v-if="s.rec"><a-tooltip :title="srv(s.rec.reason_k, s.rec.reason)"><span class="bd" :class="REC[s.rec.action][1]"><i class="dot"></i>{{ REC[s.rec.action][0] }}</span></a-tooltip><div class="sub muted rsn">{{ srv(s.rec.reason_k, s.rec.reason) }}</div></span><span v-else></span>
        <span class="muted" :title="s.cwd">{{ repoOf(s) }}</span>
        <span class="n muted">{{ s.turns }}</span>
        <span class="muted" :title="s.last ? new Date(s.last).toLocaleString($loc()) : ''">{{ s.age_min == null ? '—' : ageText(s.age_min) }}</span>
        <span @click.stop><a v-if="/^local_[0-9a-f-]{36}$/.test(s.id)" class="alink" :href="'claude://claude.ai/epitaxy/' + s.id" :title="$t('cleanup.open_tip')">{{ $t('cleanup.open') }}</a>
          <button v-if="s.first_prompt" class="alink" @click="askIdea(s)" :title="$t('cleanup.idea_tip')">{{ $t('cleanup.idea_btn') }}</button></span>
      </div>
    </div>
    <div v-if="picked.length" class="selbar"><b>{{ $t('cleanup.selected', { n: picked.length }) }}</b>
      <a-button v-if="!showArchived" type="primary" size="small" :loading="busy" @click="archive">{{ $t('cleanup.archive_selected') }}</a-button>
      <a-button v-else size="small" :loading="busy" @click="restore">{{ $t('cleanup.restore') }}</a-button>
      <a-button danger size="small" @click="askDelete">{{ $t('cleanup.delete_btn') }}</a-button></div>
    <a-modal v-model:open="idea.open" :title="$t('cleanup.idea.title')" :ok-text="$t('cleanup.idea.ok')" :cancel-text="$t('ant.cancel')" :ok-button-props="{ disabled: !idea.text.trim(), loading: idea.busy }" @ok="saveIdea">
      <p class="muted sm" style="margin-bottom:6px">{{ $t('cleanup.idea.hint', { title: idea.s && idea.s.title }) }}</p>
      <a-textarea v-model:value="idea.text" :auto-size="{ minRows: 3, maxRows: 10 }" :maxlength="2000" show-count /></a-modal>
    <a-modal v-model:open="del.open" :title="$t('cleanup.del.title', { n: del.list.length })" :ok-text="$t('cleanup.del.ok')" :cancel-text="$t('ant.cancel')" :ok-button-props="{ danger: true, disabled: del.text.trim().toLowerCase() !== confirmWord, loading: del.busy }" @ok="doDelete">
      <p>{{ $t('cleanup.del.body1') }} <code>~/.claude</code> {{ $t('cleanup.del.body2', { size: mb(del.bytes) }) }} <b>{{ $t('cleanup.del.body3') }}</b>{{ $t('cleanup.del.body4') }}</p>
      <ul class="dlist"><li v-for="s in del.list.slice(0, 8)" :key="s.id">{{ s.title || $t('cleanup.untitled') }} <span class="muted">· {{ repoOf(s) }} · {{ ageText(s.age_min) }}</span></li><li v-if="del.list.length > 8" class="muted">{{ $t('cleanup.del.more', { n: del.list.length - 8 }) }}</li></ul>
      <p v-if="rescuable.length" style="margin-bottom:8px"><a-checkbox v-model:checked="del.keep">{{ $t('cleanup.del.keep', { n: rescuable.length }) }}</a-checkbox></p>
      <p v-if="del.err" class="muted sm">{{ del.err }}</p>
      <p style="margin-bottom:4px">{{ $t('cleanup.del.confirm') }} <b>{{ confirmWord }}</b>:</p><a-input v-model:value="del.text" :placeholder="confirmWord" @press-enter="del.text.trim().toLowerCase() === confirmWord && doDelete()" /></a-modal>
  </div>`,
};
