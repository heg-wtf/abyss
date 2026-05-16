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
  asParams,
  type TestHomeHandle,
} from "./_setup";

import {
  GET as getBotRoute,
  PUT as putBotRoute,
  DELETE as deleteBotSession,
} from "../bots/[name]/route";
import {
  GET as getBotMemoryRoute,
  PUT as putBotMemoryRoute,
} from "../bots/[name]/memory/route";
import {
  GET as getCronRoute,
  PUT as putCronRoute,
} from "../bots/[name]/cron/route";
import {
  GET as getSkillRoute,
  PUT as putSkillRoute,
  DELETE as deleteSkillRoute,
} from "../skills/[name]/route";
import {
  GET as getConversationRoute,
  DELETE as deleteConversationRoute,
} from "../bots/[name]/conversations/[chatId]/[date]/route";

let handle: TestHomeHandle;

beforeEach(() => {
  handle = mountTestHome();
});

afterEach(() => {
  handle.cleanup();
});

describe("/api/bots/[name]", () => {
  it("GET returns 404 for an unknown bot", async () => {
    const res = await getBotRoute(makeRequest("/api/bots/missing"), {
      params: asParams({ name: "missing" }),
    });
    expect(res.status).toBe(404);
  });

  it("GET returns the bot with masked token + cronJobs + sessions + memory", async () => {
    setupBasicConfig(handle.home);
    writeYamlFile(path.join(handle.home, "bots", "testbot", "cron.yaml"), {
      jobs: [{ name: "morning", enabled: true, schedule: "0 9 * * *", message: "x" }],
    });
    writeFile(
      path.join(handle.home, "bots", "testbot", "MEMORY.md"),
      "remember",
    );
    const res = await getBotRoute(makeRequest("/api/bots/testbot"), {
      params: asParams({ name: "testbot" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.telegram_token).toBe("***");
    expect(body.cronJobs).toHaveLength(1);
    expect(body.memory).toBe("remember");
  });

  it("PUT persists updates to bot.yaml", async () => {
    setupBasicConfig(handle.home);
    const req = makeRequest("/api/bots/testbot", {
      method: "PUT",
      json: { goal: "new goal" },
    });
    const res = await putBotRoute(req, {
      params: asParams({ name: "testbot" }),
    });
    expect(res.status).toBe(200);
    const yamlText = fs.readFileSync(
      path.join(handle.home, "bots", "testbot", "bot.yaml"),
      "utf-8",
    );
    const data = yaml.load(yamlText) as { goal: string };
    expect(data.goal).toBe("new goal");
  });

  it("DELETE requires chatId in the body (400 when missing)", async () => {
    setupBasicConfig(handle.home);
    const req = makeRequest("/api/bots/testbot", {
      method: "DELETE",
      json: {},
    });
    const res = await deleteBotSession(req, {
      params: asParams({ name: "testbot" }),
    });
    expect(res.status).toBe(400);
  });

  it("DELETE returns 404 for an unknown session", async () => {
    setupBasicConfig(handle.home);
    const req = makeRequest("/api/bots/testbot", {
      method: "DELETE",
      json: { chatId: "ghost" },
    });
    const res = await deleteBotSession(req, {
      params: asParams({ name: "testbot" }),
    });
    expect(res.status).toBe(404);
  });

  it("DELETE removes a real session directory", async () => {
    setupBasicConfig(handle.home);
    const sessionDir = path.join(
      handle.home,
      "bots",
      "testbot",
      "sessions",
      "chat_42",
    );
    writeFile(path.join(sessionDir, "conversation-260516.md"), "x");
    const req = makeRequest("/api/bots/testbot", {
      method: "DELETE",
      json: { chatId: "42" },
    });
    const res = await deleteBotSession(req, {
      params: asParams({ name: "testbot" }),
    });
    expect(res.status).toBe(200);
    expect(fs.existsSync(sessionDir)).toBe(false);
  });
});

describe("/api/bots/[name]/memory", () => {
  it("GET returns empty content when MEMORY.md is missing", async () => {
    setupBasicConfig(handle.home);
    const res = await getBotMemoryRoute(
      makeRequest("/api/bots/testbot/memory"),
      { params: asParams({ name: "testbot" }) },
    );
    expect((await res.json()).content).toBe("");
  });

  it("PUT writes MEMORY.md and GET reads it back", async () => {
    setupBasicConfig(handle.home);
    const putReq = makeRequest("/api/bots/testbot/memory", {
      method: "PUT",
      json: { content: "remember me" },
    });
    expect(
      (
        await putBotMemoryRoute(putReq, {
          params: asParams({ name: "testbot" }),
        })
      ).status,
    ).toBe(200);

    const getReq = makeRequest("/api/bots/testbot/memory");
    const body = await (
      await getBotMemoryRoute(getReq, { params: asParams({ name: "testbot" }) })
    ).json();
    expect(body.content).toBe("remember me");
  });
});

describe("/api/bots/[name]/cron", () => {
  it("GET returns empty jobs when no cron.yaml exists", async () => {
    setupBasicConfig(handle.home);
    const res = await getCronRoute(makeRequest("/api/bots/testbot/cron"), {
      params: asParams({ name: "testbot" }),
    });
    expect((await res.json()).jobs).toEqual([]);
  });

  it("PUT persists jobs and GET reads them back", async () => {
    setupBasicConfig(handle.home);
    const jobs = [
      { name: "j", enabled: true, schedule: "0 9 * * *", message: "ping" },
    ];
    const putReq = makeRequest("/api/bots/testbot/cron", {
      method: "PUT",
      json: { jobs },
    });
    expect(
      (
        await putCronRoute(putReq, {
          params: asParams({ name: "testbot" }),
        })
      ).status,
    ).toBe(200);

    const res = await getCronRoute(makeRequest("/api/bots/testbot/cron"), {
      params: asParams({ name: "testbot" }),
    });
    const body = await res.json();
    expect(body.jobs).toEqual(jobs);
  });
});

describe("/api/skills/[name]", () => {
  it("GET returns the skill payload (config + markdown)", async () => {
    writeYamlFile(path.join(handle.home, "skills", "custom", "skill.yaml"), {
      name: "custom",
      type: "cli",
      status: "active",
      description: "mine",
      allowed_tools: [],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: [],
      install_hints: {},
    });
    writeFile(
      path.join(handle.home, "skills", "custom", "SKILL.md"),
      "# custom",
    );
    const res = await getSkillRoute(makeRequest("/api/skills/custom"), {
      params: asParams({ name: "custom" }),
    });
    const body = await res.json();
    expect(body.config.description).toBe("mine");
    expect(body.skillMarkdown).toBe("# custom");
  });

  it("PUT rejects edits to built-in skills (403)", async () => {
    const req = makeRequest("/api/skills/qmd", {
      method: "PUT",
      json: { config: {}, skillMarkdown: "" },
    });
    const res = await putSkillRoute(req, {
      params: asParams({ name: "qmd" }),
    });
    expect(res.status).toBe(403);
  });

  it("PUT returns 404 for nonexistent custom skills", async () => {
    const req = makeRequest("/api/skills/ghost", {
      method: "PUT",
      json: { config: {} },
    });
    const res = await putSkillRoute(req, {
      params: asParams({ name: "ghost" }),
    });
    expect(res.status).toBe(404);
  });

  it("DELETE rejects built-in skills (403)", async () => {
    const req = makeRequest("/api/skills/qmd", { method: "DELETE" });
    const res = await deleteSkillRoute(req, {
      params: asParams({ name: "qmd" }),
    });
    expect(res.status).toBe(403);
  });

  it("DELETE removes a custom skill directory", async () => {
    writeYamlFile(path.join(handle.home, "skills", "mine", "skill.yaml"), {
      name: "mine",
      type: "cli",
      status: "active",
      description: "",
      allowed_tools: [],
      environment_variables: [],
      environment_variable_values: {},
      required_commands: [],
      install_hints: {},
    });
    writeFile(path.join(handle.home, "skills", "mine", "SKILL.md"), "x");
    const req = makeRequest("/api/skills/mine", { method: "DELETE" });
    const res = await deleteSkillRoute(req, {
      params: asParams({ name: "mine" }),
    });
    expect(res.status).toBe(200);
    expect(fs.existsSync(path.join(handle.home, "skills", "mine"))).toBe(
      false,
    );
  });
});

describe("/api/bots/[name]/conversations/[chatId]/[date]", () => {
  it("GET returns empty content when the file is missing", async () => {
    setupBasicConfig(handle.home);
    const res = await getConversationRoute(
      makeRequest("/api/bots/testbot/conversations/1/260516"),
      {
        params: asParams({
          name: "testbot",
          chatId: "1",
          date: "260516",
        }),
      },
    );
    expect((await res.json()).content).toBe("");
  });

  it("GET returns the conversation markdown when present", async () => {
    setupBasicConfig(handle.home);
    writeFile(
      path.join(
        handle.home,
        "bots",
        "testbot",
        "sessions",
        "chat_1",
        "conversation-260516.md",
      ),
      "## user\nhello",
    );
    const res = await getConversationRoute(
      makeRequest("/api/bots/testbot/conversations/1/260516"),
      {
        params: asParams({
          name: "testbot",
          chatId: "1",
          date: "260516",
        }),
      },
    );
    expect((await res.json()).content).toContain("hello");
  });

  it("DELETE returns 404 when the file isn't there", async () => {
    setupBasicConfig(handle.home);
    const res = await deleteConversationRoute(
      makeRequest("/api/bots/testbot/conversations/1/260516", {
        method: "DELETE",
      }),
      {
        params: asParams({
          name: "testbot",
          chatId: "1",
          date: "260516",
        }),
      },
    );
    expect(res.status).toBe(404);
  });

  it("DELETE removes the conversation file when present", async () => {
    setupBasicConfig(handle.home);
    const target = path.join(
      handle.home,
      "bots",
      "testbot",
      "sessions",
      "chat_1",
      "conversation-260516.md",
    );
    writeFile(target, "x");
    const res = await deleteConversationRoute(
      makeRequest("/api/bots/testbot/conversations/1/260516", {
        method: "DELETE",
      }),
      {
        params: asParams({
          name: "testbot",
          chatId: "1",
          date: "260516",
        }),
      },
    );
    expect(res.status).toBe(200);
    expect(fs.existsSync(target)).toBe(false);
  });

  it("DELETE refuses malformed date (returns 404 from underlying validator)", async () => {
    setupBasicConfig(handle.home);
    const res = await deleteConversationRoute(
      makeRequest("/api/bots/testbot/conversations/1/bad-date", {
        method: "DELETE",
      }),
      {
        params: asParams({
          name: "testbot",
          chatId: "1",
          date: "bad-date",
        }),
      },
    );
    expect(res.status).toBe(404);
  });
});
