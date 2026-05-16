/**
 * Barrel re-exports for the abyss data layer.
 *
 * Source lives under `lib/abyss/<domain>.ts`. Import from `@/lib/abyss` (this
 * file) for stable API, or from the domain submodule for narrower deps.
 */

export { getAbyssHome } from "./abyss/paths";

export type { GlobalConfig } from "./abyss/config";
export { getConfig, updateConfig } from "./abyss/config";

export type { BotConfig } from "./abyss/bots";
export { listBots, getBot, updateBot } from "./abyss/bots";

export {
  getBotMemory,
  updateBotMemory,
  getGlobalMemory,
  updateGlobalMemory,
} from "./abyss/memory";

export type { CronJob } from "./abyss/cron";
export { getCronJobs, updateCronJobs } from "./abyss/cron";

export type { SkillConfig } from "./abyss/skills";
export {
  isBuiltinSkill,
  listSkills,
  getSkill,
  createSkill,
  updateSkill,
  deleteSkill,
  getSkillUsageByBots,
} from "./abyss/skills";

export type { SessionInfo } from "./abyss/sessions";
export {
  getBotSessions,
  deleteSession,
  deleteConversation,
  getConversation,
} from "./abyss/sessions";

export type { DaemonLogInfo } from "./abyss/logs";
export {
  listLogFiles,
  getLogContent,
  deleteLogFiles,
  getDaemonLogInfo,
  truncateDaemonLogs,
} from "./abyss/logs";

export type { SystemStatus, DiskUsage } from "./abyss/status";
export { getSystemStatus, getDiskUsage } from "./abyss/status";

export type {
  ToolMetricEvent,
  ToolMetricRow,
  BotConversationFrequency,
} from "./abyss/metrics";
export {
  readToolMetricEvents,
  getToolMetrics,
  getConversationFrequency,
} from "./abyss/metrics";

export type {
  WorkspaceTreeNode,
  WorkspaceTreeResult,
} from "./abyss/workspace";
export {
  WorkspaceAccessError,
  listBotWorkspaceTree,
} from "./abyss/workspace";
