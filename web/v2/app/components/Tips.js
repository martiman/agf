import { t } from "../i18n.js";
import { store } from "../store.js";

const N_TIPS = 21;
export default {
  setup() { return { store, TIPS: Vue.computed(() => Array.from({ length: N_TIPS }, (_, i) => t("tips." + (i + 1)))) }; },
  template: `
  <a-drawer :open="store.tips" :title="$t('tips.title')" width="520" @close="store.tips = false">
    <ul style="padding-left:18px"><li v-for="t in TIPS" style="margin-bottom:8px">{{ t }}</li></ul>
    <div class="muted" style="margin-top:12px">{{ $t('tips.sc.label') }} <a-tag>R</a-tag> {{ $t('tips.sc.refresh') }} · <a-tag>L</a-tag> {{ $t('tips.sc.legend') }} · <a-tag>I</a-tag> inbox · <a-tag>S</a-tag> {{ $t('tips.sc.list') }} · <a-tag>B</a-tag> board ·
      <a-tag>↑</a-tag><a-tag>↓</a-tag> {{ $t('tips.sc.select') }} · <a-tag>?</a-tag> {{ $t('tips.sc.tips') }} · <a-tag>Esc</a-tag> {{ $t('tips.sc.close') }}. {{ $t('tips.commands') }}</div>
  </a-drawer>`,
};
