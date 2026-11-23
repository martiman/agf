import { start } from "./store.js";
import { t, locale } from "./i18n.js";
import App from "./components/App.js";
import MasterList from "./components/MasterList.js";
import TicketDetail from "./components/TicketDetail.js";
import ApproveModal from "./components/ApproveModal.js";
import LaunchModal from "./components/LaunchModal.js";
import RefinePanel from "./components/RefinePanel.js";
import SpecChecks from "./components/SpecChecks.js";
import ListView from "./components/ListView.js";
import Legend from "./components/Legend.js";
import Tips from "./components/Tips.js";
import IdeasView from "./components/IdeasView.js";
import CleanupView from "./components/CleanupView.js";
import BoardView, { FreeCard, TicketCard } from "./components/BoardView.js";

["advancedFormat", "customParseFormat", "localeData", "quarterOfYear", "weekOfYear", "weekYear", "weekday"]
  .forEach(n => window["dayjs_plugin_" + n] && window.dayjs.extend(window["dayjs_plugin_" + n]));

const app = Vue.createApp(App);
app.use(window.antd);
app.config.globalProperties.$t = t;
app.config.globalProperties.$loc = locale;
app.config.errorHandler = (e, inst, info) => console.error("[v2]", info, ((inst && inst.$ && inst.$.type && inst.$.type.template) || "").slice(0, 70).replace(/\s+/g, " "), e);
[["MasterList", MasterList], ["TicketDetail", TicketDetail], ["ApproveModal", ApproveModal], ["LaunchModal", LaunchModal],
 ["RefinePanel", RefinePanel], ["SpecChecks", SpecChecks], ["ListView", ListView], ["Legend", Legend], ["Tips", Tips], ["BoardView", BoardView], ["CleanupView", CleanupView], ["IdeasView", IdeasView], ["FreeCard", FreeCard], ["TicketCard", TicketCard]].forEach(([n, c]) => app.component(n, c));
app.mount("#app");
start();
