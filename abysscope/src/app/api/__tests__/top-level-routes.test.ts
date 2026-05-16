import { afterEach, beforeEach, describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import {
  mountTestHome,
  setupBasicConfig,
  writeFile,
  writeYamlFile,
  makeRequest,
  type TestHomeHandle,
} from "./_setup";

import { GET as getStatus } from "../status/route";
import { GET as getConfig, PUT as putConfig } from "../config/route";
import {
  GET as getGlobalMemory,
  PUT as putGlobalMemory,
} from "../global-memory/route";
import { GET as listBotsHandler } from "../bots/route";
import {
  GET as listSkillsHandler,
  POST as createSkillHandler,
} from "../skills/route";
import { GET as getLogs, DELETE as deleteLogs } from "../logs/route";

let handle: TestHomeHandle;

beforeEach(() => {
  handle = mountTestHome();
});

afterEach(() => {
  handle.cleanup();
});

describe("/api/status", () => {
  it("returns running:false + falls back to UTC when no config exists", async () => {
    const res = await getStatus();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.running).toBe(false);
    expect(body.timezone).toBe("UTC");
    expect(body.language).toBe("English");
  });

  it("includes timezone + language + log level from config", async () => {
    setupBasicConfig(handle.home);
    const res = await getStatus();
    const body = await res.json();
    expect(body.timezone).toBe("Asia/Seoul");
    expect(body.language).toBe("Korean");
    expect(body.logLevel).toBe("INFO");
    expect(body.commandTimeout).toBe(120);
  });
});

describe("/api/config", () => {
  it("returns 404 when config.yaml is missing", async () => {
    const res = await getConfig();
    expect(res.status).toBe(404);
  });

  it("returns the config payload on GET", async () => {
    setupBasicConfig(handle.home);
    const res = await getConfig();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.timezone).toBe("Asia/Seoul");
  });

  it("persists updates via PUT", async () => {
    setupBasicConfig(handle.home);
    const req = makeRequest("/api/config", {
      method: "PUT",
      json: {
        bots: [],
        timezone: "UTC",
        language: "English",
        settings: { command_timeout: 60, log_level: "DEBUG" },
      },
    });
    const res = await putConfig(req);
    expect(res.status).toBe(200);
    const persisted = yaml.load(
      fs.readFileSync(path.join(handle.home, "config.yaml"), "utf-8"),
    ) as { timezone: string; language: string };
    expect(persisted.timezone).toBe("UTC");
    expect(persisted.language).toBe("English");
  });
});

describe("/api/global-memory", () => {
  it("returns empty string when GLOBAL_MEMORY.md is absent", async () => {
    const res = await getGlobalMemory();
    const body = await res.json();
    expect(body.content).toBe("");
  });

  it("round-trips content through PUT → GET", async () => {
    const putReq = makeRequest("/api/global-memory", {
      method: "PUT",
      json: { content: "remember this" },
    });
    expect((await putGlobalMemory(putReq)).status).toBe(200);

    const res = await getGlobalMemory();
    expect((await res.json()).content).toBe("remember this");
  });
});

describe("/api/bots", () => {
  it("returns an empty list when no bots are configured", async () => {
    const res = await listBotsHandler();
    const body = await res.json();
    expect(body).toEqual([]);
  });

  it("masks the telegram token and enriches each bot with counts", async () => {
    setupBasicConfig(handle.home);
    writeYamlFile(path.join(handle.home, "bots", "testbot", "cron.yaml"), {
      jobs: [
        { name: "morning", enabled: true, schedule: "0 9 * * *", message: "x" },
      ],
    });
    const res = await listBotsHandler();
    const body = await res.json();
    expect(body).toHaveLength(1);
    expect(body[0].name).toBe("testbot");
    expect(body[0].telegram_token).toBe("***");
    expect(body[0].cronJobCount).toBe(1);
    expect(body[0].sessionCount).toBe(0);
    expect(body[0].lastActivity).toBeNull();
  });
});

describe("/api/skills", () => {
  it("returns empty list when no skills directory exists", async () => {
    const res = await listSkillsHandler();
    expect(await res.json()).toEqual([]);
  });

  it("marks built-in skills with isBuiltin and forwards usedBy", async () => {
    setupBasicConfig(handle.home);
    writeYamlFile(path.join(handle.home, "skills", "qmd", "skill.yaml"), {
      name: "qmd",
      type: "cli",
      status: "active",
      description: "search",
      allowed_tools: [],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: [],
      install_hints: {},
    });
    writeFile(path.join(handle.home, "skills", "qmd", "SKILL.md"), "# qmd");

    const res = await listSkillsHandler();
    const body = await res.json();
    expect(body).toHaveLength(1);
    expect(body[0].name).toBe("qmd");
    expect(body[0].isBuiltin).toBe(true);
    expect(body[0].usedBy).toEqual(["testbot"]);
  });

  it("POST rejects skills without a name", async () => {
    const req = makeRequest("/api/skills", {
      method: "POST",
      json: { config: {}, skillMarkdown: "" },
    });
    const res = await createSkillHandler(req);
    expect(res.status).toBe(400);
  });

  it("POST creates a new skill and returns 201", async () => {
    const req = makeRequest("/api/skills", {
      method: "POST",
      json: {
        name: "custom",
        config: { description: "mine" },
        skillMarkdown: "# custom",
      },
    });
    const res = await createSkillHandler(req);
    expect(res.status).toBe(201);
    expect(
      fs.existsSync(path.join(handle.home, "skills", "custom", "skill.yaml")),
    ).toBe(true);
  });

  it("POST returns 409 when the skill already exists", async () => {
    setupBasicConfig(handle.home);
    writeYamlFile(path.join(handle.home, "skills", "qmd", "skill.yaml"), {
      name: "qmd",
      type: "cli",
      status: "active",
      description: "",
      allowed_tools: [],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: [],
      install_hints: {},
    });
    writeFile(path.join(handle.home, "skills", "qmd", "SKILL.md"), "# qmd");

    const req = makeRequest("/api/skills", {
      method: "POST",
      json: { name: "qmd", config: {}, skillMarkdown: "" },
    });
    const res = await createSkillHandler(req);
    expect(res.status).toBe(409);
  });
});

describe("/api/logs", () => {
  it("lists log files and daemon log info", async () => {
    writeFile(path.join(handle.home, "logs", "abyss-260515.log"), "line\n");
    writeFile(path.join(handle.home, "logs", "abyss-260516.log"), "row\n");
    writeFile(path.join(handle.home, "logs", "daemon-stdout.log"), "hi");

    const req = makeRequest("/api/logs");
    const body = await (await getLogs(req)).json();
    // newest first
    expect(body.files[0]).toBe("abyss-260516.log");
    expect(body.daemonLogs).toHaveLength(2);
    const stdout = body.daemonLogs.find(
      (entry: { name: string }) => entry.name === "daemon-stdout.log",
    );
    expect(stdout.exists).toBe(true);
  });

  it("returns paged content when ?file=... is provided", async () => {
    writeFile(
      path.join(handle.home, "logs", "abyss-260516.log"),
      Array.from({ length: 10 }, (_, i) => `line ${i}`).join("\n"),
    );
    const req = makeRequest("/api/logs?file=abyss-260516.log&offset=2&limit=3");
    const body = await (await getLogs(req)).json();
    expect(body.lines).toEqual(["line 2", "line 3", "line 4"]);
    expect(body.totalLines).toBe(10);
  });

  it("DELETE truncate-daemon truncates daemon files in place", async () => {
    writeFile(path.join(handle.home, "logs", "daemon-stdout.log"), "old");
    writeFile(path.join(handle.home, "logs", "daemon-stderr.log"), "stderr");

    const req = makeRequest("/api/logs", {
      method: "DELETE",
      json: { action: "truncate-daemon" },
    });
    const body = await (await deleteLogs(req)).json();
    expect(body.truncated).toBe(2);
    expect(
      fs.statSync(path.join(handle.home, "logs", "daemon-stdout.log")).size,
    ).toBe(0);
  });

  it("DELETE files removes by exact filename", async () => {
    writeFile(path.join(handle.home, "logs", "abyss-260515.log"), "a");
    writeFile(path.join(handle.home, "logs", "abyss-260516.log"), "b");
    const req = makeRequest("/api/logs", {
      method: "DELETE",
      json: { files: ["abyss-260515.log"] },
    });
    const body = await (await deleteLogs(req)).json();
    expect(body.deleted).toBe(1);
    expect(
      fs.existsSync(path.join(handle.home, "logs", "abyss-260515.log")),
    ).toBe(false);
    expect(
      fs.existsSync(path.join(handle.home, "logs", "abyss-260516.log")),
    ).toBe(true);
  });

  it("DELETE files rejects empty / missing array with 400", async () => {
    const req = makeRequest("/api/logs", {
      method: "DELETE",
      json: { files: [] },
    });
    const res = await deleteLogs(req);
    expect(res.status).toBe(400);
  });
});
