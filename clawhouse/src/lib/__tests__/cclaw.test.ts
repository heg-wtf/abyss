import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "fs";
import path from "path";
import os from "os";
import yaml from "js-yaml";
import {
  getConfig,
  updateConfig,
  listBots,
  getBot,
  updateBot,
  getBotMemory,
  updateBotMemory,
  getCronJobs,
  updateCronJobs,
  isBuiltinSkill,
  listSkills,
  getSkill,
  getBotSessions,
  getConversation,
  getGlobalMemory,
  updateGlobalMemory,
  listLogFiles,
  getLogContent,
  getSystemStatus,
  getDiskUsage,
  getSkillUsageByBots,
  deleteLogFiles,
  deleteSession,
  deleteConversation,
  createSkill,
  updateSkill,
  deleteSkill,
} from "../cclaw";

let testHome: string;
const originalCclawHome = process.env.CCLAW_HOME;

function writeYamlFile(filePath: string, data: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, yaml.dump(data), "utf-8");
}

function writeFile(filePath: string, content: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf-8");
}

function setupTestHome(): void {
  testHome = fs.mkdtempSync(path.join(os.tmpdir(), "clawhouse-test-"));
  process.env.CCLAW_HOME = testHome;
}

function setupBasicConfig(): void {
  writeYamlFile(path.join(testHome, "config.yaml"), {
    bots: [
      { name: "testbot", path: "bots/testbot" },
      { name: "otherbot", path: "bots/otherbot" },
    ],
    timezone: "Asia/Seoul",
    language: "Korean",
    settings: {
      command_timeout: 120,
      log_level: "INFO",
    },
  });

  writeYamlFile(path.join(testHome, "bots", "testbot", "bot.yaml"), {
    telegram_token: "123:ABC",
    telegram_username: "test_user",
    telegram_botname: "testbot",
    display_name: "Test Bot",
    personality: "Helpful assistant",
    role: "assistant",
    goal: "Help users",
    model: "sonnet",
    streaming: true,
    skills: ["imessage", "reminders", "custom-skill"],
    allowed_users: ["12345"],
  });

  writeYamlFile(path.join(testHome, "bots", "otherbot", "bot.yaml"), {
    telegram_token: "456:DEF",
    telegram_username: "other_user",
    telegram_botname: "otherbot",
    display_name: "Other Bot",
    personality: "Smart bot",
    role: "analyst",
    goal: "Analyze data",
    model: "opus",
    streaming: false,
    skills: ["imessage", "dart"],
    allowed_users: [],
  });
}

beforeEach(() => {
  setupTestHome();
});

afterEach(() => {
  if (originalCclawHome) {
    process.env.CCLAW_HOME = originalCclawHome;
  } else {
    delete process.env.CCLAW_HOME;
  }
  fs.rmSync(testHome, { recursive: true, force: true });
});

// --- Config ---

describe("getConfig", () => {
  it("returns null when config.yaml does not exist", () => {
    expect(getConfig()).toBeNull();
  });

  it("reads config.yaml correctly", () => {
    setupBasicConfig();
    const config = getConfig();
    expect(config).not.toBeNull();
    expect(config!.timezone).toBe("Asia/Seoul");
    expect(config!.language).toBe("Korean");
    expect(config!.bots).toHaveLength(2);
    expect(config!.settings.log_level).toBe("INFO");
  });
});

describe("updateConfig", () => {
  it("writes config.yaml", () => {
    const config = {
      bots: [{ name: "newbot", path: "bots/newbot" }],
      timezone: "UTC",
      language: "English",
      settings: { command_timeout: 60, log_level: "DEBUG" },
    };
    updateConfig(config);
    const result = getConfig();
    expect(result).not.toBeNull();
    expect(result!.timezone).toBe("UTC");
    expect(result!.bots).toHaveLength(1);
  });
});

// --- Bots ---

describe("listBots", () => {
  it("returns empty array when no config", () => {
    expect(listBots()).toEqual([]);
  });

  it("lists all bots with merged name", () => {
    setupBasicConfig();
    const bots = listBots();
    expect(bots).toHaveLength(2);
    expect(bots[0].name).toBe("testbot");
    expect(bots[0].display_name).toBe("Test Bot");
    expect(bots[1].name).toBe("otherbot");
  });

  it("skips bots with missing bot.yaml", () => {
    writeYamlFile(path.join(testHome, "config.yaml"), {
      bots: [
        { name: "exists", path: "bots/exists" },
        { name: "missing", path: "bots/missing" },
      ],
      timezone: "UTC",
      language: "English",
      settings: { command_timeout: 60, log_level: "INFO" },
    });
    writeYamlFile(path.join(testHome, "bots", "exists", "bot.yaml"), {
      telegram_token: "t",
      model: "sonnet",
    });
    const bots = listBots();
    expect(bots).toHaveLength(1);
    expect(bots[0].name).toBe("exists");
  });
});

describe("getBot", () => {
  it("returns null for nonexistent bot", () => {
    setupBasicConfig();
    expect(getBot("nonexistent")).toBeNull();
  });

  it("returns bot config with name", () => {
    setupBasicConfig();
    const bot = getBot("testbot");
    expect(bot).not.toBeNull();
    expect(bot!.name).toBe("testbot");
    expect(bot!.model).toBe("sonnet");
    expect(bot!.skills).toContain("imessage");
  });
});

describe("updateBot", () => {
  it("updates bot.yaml fields", () => {
    setupBasicConfig();
    updateBot("testbot", { model: "opus", streaming: false });
    const bot = getBot("testbot");
    expect(bot!.model).toBe("opus");
    expect(bot!.streaming).toBe(false);
    expect(bot!.display_name).toBe("Test Bot");
  });

  it("does nothing for nonexistent bot", () => {
    setupBasicConfig();
    updateBot("nonexistent", { model: "opus" });
    // should not throw
  });
});

// --- Bot Memory ---

describe("getBotMemory / updateBotMemory", () => {
  it("returns empty string when no MEMORY.md", () => {
    setupBasicConfig();
    expect(getBotMemory("testbot")).toBe("");
  });

  it("reads and writes MEMORY.md", () => {
    setupBasicConfig();
    updateBotMemory("testbot", "# Bot Memory\nRemember this.");
    expect(getBotMemory("testbot")).toBe("# Bot Memory\nRemember this.");
  });

  it("returns empty for nonexistent bot", () => {
    setupBasicConfig();
    expect(getBotMemory("nonexistent")).toBe("");
  });
});

// --- Cron Jobs ---

describe("getCronJobs / updateCronJobs", () => {
  it("returns empty array when no cron.yaml", () => {
    setupBasicConfig();
    expect(getCronJobs("testbot")).toEqual([]);
  });

  it("reads cron jobs", () => {
    setupBasicConfig();
    writeYamlFile(path.join(testHome, "bots", "testbot", "cron.yaml"), {
      jobs: [
        {
          name: "morning",
          enabled: true,
          schedule: "0 9 * * *",
          message: "Good morning",
        },
        {
          name: "evening",
          enabled: false,
          schedule: "0 21 * * *",
          message: "Good evening",
        },
      ],
    });
    const jobs = getCronJobs("testbot");
    expect(jobs).toHaveLength(2);
    expect(jobs[0].name).toBe("morning");
    expect(jobs[1].enabled).toBe(false);
  });

  it("writes cron jobs", () => {
    setupBasicConfig();
    updateCronJobs("testbot", [
      {
        name: "daily",
        enabled: true,
        schedule: "0 8 * * *",
        message: "Check tasks",
      },
    ]);
    const jobs = getCronJobs("testbot");
    expect(jobs).toHaveLength(1);
    expect(jobs[0].name).toBe("daily");
  });

  it("reads one-shot cron jobs with at and delete_after_run fields", () => {
    setupBasicConfig();
    writeYamlFile(path.join(testHome, "bots", "testbot", "cron.yaml"), {
      jobs: [
        {
          name: "one-shot-task",
          enabled: true,
          at: "2026-03-25T15:00:00",
          message: "Run once",
          delete_after_run: true,
        },
        {
          name: "recurring-with-skills",
          enabled: true,
          schedule: "0 9 * * *",
          message: "Daily check",
          skills: ["imessage", "gmail"],
        },
      ],
    });
    const jobs = getCronJobs("testbot");
    expect(jobs).toHaveLength(2);
    expect(jobs[0].at).toBe("2026-03-25T15:00:00");
    expect(jobs[0].delete_after_run).toBe(true);
    expect(jobs[0].schedule).toBeUndefined();
    expect(jobs[1].skills).toEqual(["imessage", "gmail"]);
    expect(jobs[1].at).toBeUndefined();
  });

  it("writes one-shot cron jobs preserving at and delete_after_run", () => {
    setupBasicConfig();
    updateCronJobs("testbot", [
      {
        name: "reminder",
        enabled: true,
        message: "Remind me",
        at: "2026-04-01T10:00:00",
        delete_after_run: true,
      },
    ]);
    const jobs = getCronJobs("testbot");
    expect(jobs).toHaveLength(1);
    expect(jobs[0].at).toBe("2026-04-01T10:00:00");
    expect(jobs[0].delete_after_run).toBe(true);
  });
});

// --- Skills ---

describe("isBuiltinSkill", () => {
  it("returns true for builtin skills", () => {
    expect(isBuiltinSkill("imessage")).toBe(true);
    expect(isBuiltinSkill("supabase")).toBe(true);
    expect(isBuiltinSkill("dart")).toBe(true);
    expect(isBuiltinSkill("gmail")).toBe(true);
    expect(isBuiltinSkill("qmd")).toBe(true);
  });

  it("returns false for custom skills", () => {
    expect(isBuiltinSkill("custom-skill")).toBe(false);
    expect(isBuiltinSkill("my-tool")).toBe(false);
    expect(isBuiltinSkill("")).toBe(false);
  });
});

describe("listSkills", () => {
  it("returns empty array when skills directory does not exist", () => {
    expect(listSkills()).toEqual([]);
  });

  it("lists skills from skill.yaml files", () => {
    writeYamlFile(path.join(testHome, "skills", "naver-search", "skill.yaml"), {
      name: "naver-search",
      type: "cli",
      status: "active",
      description: "Naver search",
      allowed_tools: [],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: ["naver-cli"],
      install_hints: {},
    });
    writeYamlFile(path.join(testHome, "skills", "supabase", "skill.yaml"), {
      name: "supabase",
      type: "mcp",
      status: "active",
      description: "Supabase MCP",
      allowed_tools: ["mcp__supabase*"],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: [],
      install_hints: {},
    });
    const skills = listSkills();
    expect(skills).toHaveLength(2);
    const names = skills.map((s) => s.name);
    expect(names).toContain("naver-search");
    expect(names).toContain("supabase");
  });

  it("skips directories without skill.yaml", () => {
    fs.mkdirSync(path.join(testHome, "skills", "empty-skill"), {
      recursive: true,
    });
    writeYamlFile(path.join(testHome, "skills", "valid", "skill.yaml"), {
      name: "valid",
      type: "cli",
      status: "active",
      description: "Valid skill",
    });
    const skills = listSkills();
    expect(skills).toHaveLength(1);
    expect(skills[0].name).toBe("valid");
  });
});

describe("getSkill", () => {
  it("returns null config for nonexistent skill", () => {
    const result = getSkill("nonexistent");
    expect(result.config).toBeNull();
    expect(result.skillMarkdown).toBe("");
    expect(result.mcpConfig).toBeNull();
  });

  it("reads skill.yaml, SKILL.md, and mcp.json", () => {
    const skillDir = path.join(testHome, "skills", "supabase");
    writeYamlFile(path.join(skillDir, "skill.yaml"), {
      name: "supabase",
      type: "mcp",
      status: "active",
      description: "Supabase",
    });
    writeFile(path.join(skillDir, "SKILL.md"), "# Supabase Skill");
    writeFile(
      path.join(skillDir, "mcp.json"),
      JSON.stringify({ mcpServers: { supabase: {} } }),
    );

    const result = getSkill("supabase");
    expect(result.config!.name).toBe("supabase");
    expect(result.config!.type).toBe("mcp");
    expect(result.skillMarkdown).toBe("# Supabase Skill");
    expect(result.mcpConfig).toEqual({ mcpServers: { supabase: {} } });
  });
});

describe("createSkill / updateSkill / deleteSkill", () => {
  it("creates a new skill with directory and files", () => {
    const created = createSkill(
      "my-tool",
      { description: "My custom tool" },
      "# My Tool\n\nInstructions",
    );
    expect(created).toBe(true);
    const skill = getSkill("my-tool");
    expect(skill.config?.name).toBe("my-tool");
    expect(skill.config?.description).toBe("My custom tool");
    expect(skill.skillMarkdown).toBe("# My Tool\n\nInstructions");
  });

  it("rejects creating a skill that already exists", () => {
    createSkill("existing", { description: "First" }, "# First");
    const duplicate = createSkill(
      "existing",
      { description: "Second" },
      "# Second",
    );
    expect(duplicate).toBe(false);
    expect(getSkill("existing").config?.description).toBe("First");
  });

  it("updates an existing skill config and markdown", () => {
    createSkill("editable", { description: "Before" }, "# Before");
    const updated = updateSkill(
      "editable",
      { description: "After", emoji: "🔧" },
      "# After",
    );
    expect(updated).toBe(true);
    const skill = getSkill("editable");
    expect(skill.config?.description).toBe("After");
    expect(skill.config?.emoji).toBe("🔧");
    expect(skill.skillMarkdown).toBe("# After");
  });

  it("returns false when updating nonexistent skill", () => {
    expect(updateSkill("nonexistent", { description: "x" })).toBe(false);
  });

  it("deletes a skill directory", () => {
    createSkill("deletable", { description: "Gone soon" }, "# Delete me");
    expect(listSkills().some((s) => s.name === "deletable")).toBe(true);
    const deleted = deleteSkill("deletable");
    expect(deleted).toBe(true);
    expect(listSkills().some((s) => s.name === "deletable")).toBe(false);
  });
});

// --- Sessions ---

describe("getBotSessions", () => {
  it("returns empty array for bot with no sessions", () => {
    setupBasicConfig();
    expect(getBotSessions("testbot")).toEqual([]);
  });

  it("lists sessions with conversation files", () => {
    setupBasicConfig();
    const sessionDir = path.join(
      testHome,
      "bots",
      "testbot",
      "sessions",
      "chat_12345",
    );
    writeFile(
      path.join(sessionDir, "conversation-260310.md"),
      "# Conversation",
    );
    writeFile(
      path.join(sessionDir, "conversation-260311.md"),
      "# Conversation 2",
    );
    writeFile(path.join(sessionDir, ".claude_session_id"), "uuid-123");

    const sessions = getBotSessions("testbot");
    expect(sessions).toHaveLength(1);
    expect(sessions[0].chatId).toBe("12345");
    expect(sessions[0].conversationFiles).toHaveLength(2);
    expect(sessions[0].hasSessionId).toBe(true);
    expect(sessions[0].lastActivity).not.toBeNull();
  });

  it("ignores non-chat directories", () => {
    setupBasicConfig();
    fs.mkdirSync(
      path.join(testHome, "bots", "testbot", "sessions", "not_a_chat"),
      { recursive: true },
    );
    fs.mkdirSync(
      path.join(testHome, "bots", "testbot", "sessions", "chat_999"),
      { recursive: true },
    );
    const sessions = getBotSessions("testbot");
    expect(sessions).toHaveLength(1);
    expect(sessions[0].chatId).toBe("999");
  });
});

describe("getConversation", () => {
  it("returns empty string for nonexistent conversation", () => {
    setupBasicConfig();
    expect(getConversation("testbot", "12345", "260310")).toBe("");
  });

  it("reads conversation file content", () => {
    setupBasicConfig();
    writeFile(
      path.join(
        testHome,
        "bots",
        "testbot",
        "sessions",
        "chat_12345",
        "conversation-260310.md",
      ),
      "User: Hello\nAssistant: Hi!",
    );
    const content = getConversation("testbot", "12345", "260310");
    expect(content).toBe("User: Hello\nAssistant: Hi!");
  });
});

describe("deleteConversation", () => {
  it("deletes a specific conversation file", () => {
    setupBasicConfig();
    const sessionDir = path.join(
      testHome,
      "bots",
      "testbot",
      "sessions",
      "chat_12345",
    );
    writeFile(path.join(sessionDir, "conversation-260310.md"), "# Day 1");
    writeFile(path.join(sessionDir, "conversation-260311.md"), "# Day 2");

    const result = deleteConversation("testbot", "12345", "260310");
    expect(result).toBe(true);
    expect(fs.existsSync(path.join(sessionDir, "conversation-260310.md"))).toBe(
      false,
    );
    expect(fs.existsSync(path.join(sessionDir, "conversation-260311.md"))).toBe(
      true,
    );
  });

  it("returns false for nonexistent file", () => {
    setupBasicConfig();
    expect(deleteConversation("testbot", "12345", "999999")).toBe(false);
  });

  it("rejects invalid date format", () => {
    setupBasicConfig();
    expect(deleteConversation("testbot", "12345", "../hack")).toBe(false);
  });
});

describe("deleteSession", () => {
  it("deletes an existing session directory", () => {
    setupBasicConfig();
    const sessionDir = path.join(
      testHome,
      "bots",
      "testbot",
      "sessions",
      "chat_12345",
    );
    writeFile(path.join(sessionDir, "conversation-260310.md"), "# Test");
    writeFile(path.join(sessionDir, ".claude_session_id"), "uuid-123");

    expect(getBotSessions("testbot")).toHaveLength(1);
    const result = deleteSession("testbot", "12345");
    expect(result).toBe(true);
    expect(getBotSessions("testbot")).toHaveLength(0);
    expect(fs.existsSync(sessionDir)).toBe(false);
  });

  it("returns false for nonexistent bot", () => {
    expect(deleteSession("nonexistent", "12345")).toBe(false);
  });

  it("returns true for nonexistent session (rmSync force)", () => {
    setupBasicConfig();
    const result = deleteSession("testbot", "99999");
    expect(result).toBe(true);
  });
});

// --- Global Memory ---

describe("getGlobalMemory / updateGlobalMemory", () => {
  it("returns empty string when no file", () => {
    expect(getGlobalMemory()).toBe("");
  });

  it("reads and writes GLOBAL_MEMORY.md", () => {
    updateGlobalMemory("# Global\nShared info.");
    expect(getGlobalMemory()).toBe("# Global\nShared info.");
  });
});

// --- Logs ---

describe("listLogFiles", () => {
  it("returns empty array when no logs directory", () => {
    expect(listLogFiles()).toEqual([]);
  });

  it("lists log files in reverse order", () => {
    const logsDir = path.join(testHome, "logs");
    writeFile(path.join(logsDir, "cclaw-260308.log"), "log1");
    writeFile(path.join(logsDir, "cclaw-260309.log"), "log2");
    writeFile(path.join(logsDir, "cclaw-260310.log"), "log3");
    writeFile(path.join(logsDir, "other.txt"), "not a log");

    const logs = listLogFiles();
    expect(logs).toHaveLength(3);
    expect(logs[0]).toBe("cclaw-260310.log");
    expect(logs[2]).toBe("cclaw-260308.log");
  });
});

describe("getLogContent", () => {
  it("returns empty for nonexistent log", () => {
    const result = getLogContent("cclaw-260310.log");
    expect(result.lines).toEqual([]);
    expect(result.totalLines).toBe(0);
  });

  it("reads log with pagination", () => {
    writeFile(
      path.join(testHome, "logs", "cclaw-260310.log"),
      "line1\nline2\nline3\nline4\nline5",
    );
    const full = getLogContent("cclaw-260310.log");
    expect(full.totalLines).toBe(5);
    expect(full.lines).toHaveLength(5);

    const page = getLogContent("cclaw-260310.log", 1, 2);
    expect(page.lines).toEqual(["line2", "line3"]);
    expect(page.totalLines).toBe(5);
  });
});

describe("deleteLogFiles", () => {
  it("deletes specified log files", () => {
    const logsDir = path.join(testHome, "logs");
    writeFile(path.join(logsDir, "cclaw-260308.log"), "log1");
    writeFile(path.join(logsDir, "cclaw-260309.log"), "log2");
    writeFile(path.join(logsDir, "cclaw-260310.log"), "log3");

    const deleted = deleteLogFiles(["cclaw-260308.log", "cclaw-260309.log"]);
    expect(deleted).toBe(2);
    expect(listLogFiles()).toEqual(["cclaw-260310.log"]);
  });

  it("ignores nonexistent files", () => {
    const deleted = deleteLogFiles(["cclaw-999999.log"]);
    expect(deleted).toBe(0);
  });

  it("rejects invalid filenames", () => {
    const logsDir = path.join(testHome, "logs");
    writeFile(path.join(logsDir, "cclaw-260308.log"), "log1");
    writeFile(path.join(logsDir, "other.txt"), "not a log");

    const deleted = deleteLogFiles([
      "../config.yaml",
      "other.txt",
      "cclaw-260308.log",
    ]);
    expect(deleted).toBe(1);
    expect(fs.existsSync(path.join(logsDir, "other.txt"))).toBe(true);
  });
});

// --- System Status ---

describe("getSystemStatus", () => {
  it("returns not running when no pid file", () => {
    const status = getSystemStatus();
    expect(status.running).toBe(false);
    expect(status.pid).toBeNull();
  });

  it("returns running for current process pid", () => {
    writeFile(path.join(testHome, "cclaw.pid"), String(process.pid));
    const status = getSystemStatus();
    expect(status.running).toBe(true);
    expect(status.pid).toBe(process.pid);
  });

  it("returns not running for stale pid", () => {
    writeFile(path.join(testHome, "cclaw.pid"), "999999999");
    const status = getSystemStatus();
    expect(status.running).toBe(false);
  });
});

// --- Disk Usage ---

describe("getDiskUsage", () => {
  it("returns zero when CCLAW_HOME is empty", () => {
    const usage = getDiskUsage();
    expect(usage.totalBytes).toBe(0);
    expect(usage.breakdown).toEqual([]);
  });

  it("calculates disk usage with breakdown", () => {
    writeFile(path.join(testHome, "config.yaml"), "timezone: UTC");
    writeFile(
      path.join(testHome, "bots", "testbot", "bot.yaml"),
      "model: sonnet",
    );
    writeFile(
      path.join(testHome, "logs", "cclaw-260310.log"),
      "a]".repeat(1000),
    );

    const usage = getDiskUsage();
    expect(usage.totalBytes).toBeGreaterThan(0);
    expect(usage.breakdown.length).toBeGreaterThanOrEqual(3);
    expect(usage.totalFormatted).toBeTruthy();

    // breakdown should be sorted descending by size
    for (let i = 1; i < usage.breakdown.length; i++) {
      expect(usage.breakdown[i - 1].bytes).toBeGreaterThanOrEqual(
        usage.breakdown[i].bytes,
      );
    }
  });

  it("formats bytes correctly", () => {
    // Create a file just to get some disk usage
    writeFile(path.join(testHome, "small.txt"), "hello");
    const usage = getDiskUsage();
    const small = usage.breakdown.find((b) => b.name === "small.txt");
    expect(small).toBeDefined();
    expect(small!.formatted).toBe("5 B");
  });
});

// --- Skill Usage ---

describe("getSkillUsageByBots", () => {
  it("returns empty when no bots", () => {
    expect(getSkillUsageByBots()).toEqual({});
  });

  it("maps skills to bot names", () => {
    setupBasicConfig();
    const usage = getSkillUsageByBots();
    expect(usage["imessage"]).toEqual(["testbot", "otherbot"]);
    expect(usage["reminders"]).toEqual(["testbot"]);
    expect(usage["dart"]).toEqual(["otherbot"]);
    expect(usage["custom-skill"]).toEqual(["testbot"]);
  });
});
