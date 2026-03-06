/**
 * cclaw-bridge: Node.js bridge for Claude Code SDK.
 *
 * Runs Claude Code queries via the Agent SDK's v1 query() function,
 * avoiding the overhead of spawning a new `claude` process per message.
 * Listens on a Unix socket, accepts JSONL requests from Python.
 *
 * Protocol (JSONL over Unix socket):
 *   Request:  { action, sessionKey, prompt, cwd, model, ... }
 *   Response: { type: "text"|"result"|"error", ... }  (one per line)
 *
 * Note on SDK versions:
 *   - v1 query(): Spawns full Claude Code internally. Reads CLAUDE.md,
 *     supports Bash tools, skills, and all Claude Code features.
 *   - v2 unstable_v2_prompt/createSession: Alpha API that calls Anthropic
 *     API directly. Does NOT read CLAUDE.md or support Bash tools.
 *     Will be reconsidered when v2 matures and supports tool execution.
 *     See: https://platform.claude.com/docs/en/agent-sdk/typescript-v2-preview
 */

import net from "node:net";
import fs from "node:fs";

const SOCKET_PATH = process.env.CCLAW_BRIDGE_SOCKET || "/tmp/cclaw-bridge.sock";
const LOG_PATH = process.env.CCLAW_BRIDGE_LOG || "/tmp/cclaw-bridge.log";

// ─── Logging ────────────────────────────────────────────────────────────────

const logStream = fs.createWriteStream(LOG_PATH, { flags: "a" });

function log(...args) {
  const timestamp = new Date().toISOString();
  const message = `[${timestamp}] [bridge] ${args.join(" ")}`;
  logStream.write(message + "\n");
  process.stderr.write(message + "\n");
}

// Clean up stale socket file
if (fs.existsSync(SOCKET_PATH)) {
  fs.unlinkSync(SOCKET_PATH);
}

// ─── SDK Import ─────────────────────────────────────────────────────────────

let sdkQuery;

try {
  const sdk = await import("@anthropic-ai/claude-agent-sdk");
  sdkQuery = sdk.query;
  log(`SDK loaded (query: ${!!sdkQuery})`);
} catch (error) {
  log("Failed to load SDK:", error.message);
  process.exit(1);
}

// ─── Request Handler ────────────────────────────────────────────────────────

async function handleQuery(connection, request) {
  const {
    sessionKey,
    prompt,
    cwd,
    model,
    sessionId,
    resume,
    permissionMode = "acceptEdits",
    allowedTools,
    disallowedTools,
    systemPrompt,
    mcpServers,
    env,
    streaming = false,
  } = request;

  const options = {};
  if (cwd) options.cwd = cwd;
  if (model) options.model = model;
  if (permissionMode) options.permissionMode = permissionMode;
  if (allowedTools) options.allowedTools = allowedTools;
  if (disallowedTools) options.disallowedTools = disallowedTools;
  if (systemPrompt) options.systemPrompt = systemPrompt;
  if (mcpServers) options.mcpServers = mcpServers;
  if (env) options.env = { ...process.env, ...env };

  if (resume && sessionId) {
    options.resume = sessionId;
  } else if (sessionId) {
    options.sessionId = sessionId;
  }

  log(`query for ${sessionKey}: cwd=${cwd}, model=${model}, resume=${!!resume}, sessionId=${sessionId?.slice(0, 8) || "none"}`);

  // Run query, retry without session if session ID is stale
  try {
    await runQuery(connection, sessionKey, prompt, options, streaming);
  } catch (error) {
    if ((options.resume || options.sessionId) &&
        (error.message?.includes("session") || error.message?.includes("conversation"))) {
      log(`Session error, retrying without session: ${error.message}`);
      delete options.resume;
      delete options.sessionId;
      await runQuery(connection, sessionKey, prompt, options, streaming);
    } else {
      throw error;
    }
  }
}

async function runQuery(connection, sessionKey, prompt, options, streaming) {
  log(`query start for ${sessionKey}: "${prompt.slice(0, 80)}"`);

  let resultText = "";
  let resultSessionId = "";

  for await (const message of sdkQuery({ prompt, options })) {
    if (message.session_id) {
      resultSessionId = message.session_id;
    }

    if (message.type === "assistant") {
      const text = extractAssistantText(message);
      if (text && streaming) {
        writeLine(connection, { type: "text", text });
      }
      if (text) resultText = text;
    }

    if (message.type === "result") {
      log(`query result subtype=${message.subtype}, length=${(message.result || "").length}`);
      resultText = message.result || resultText;
      resultSessionId = message.session_id || resultSessionId;
    }
  }

  log(`query done (${resultText.length} chars): ${resultText.slice(0, 100)}`);
  writeLine(connection, {
    type: "result",
    text: resultText,
    sessionId: resultSessionId,
  });
}

function handleHealth(connection) {
  writeLine(connection, {
    type: "health",
    status: "ok",
    uptime: process.uptime(),
  });
}

// ─── Utility ───────────────────────────────────────────────────────────────

function extractAssistantText(message) {
  if (!message.message?.content) return null;
  return message.message.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("");
}

function writeLine(connection, data) {
  if (!connection.destroyed) {
    connection.write(JSON.stringify(data) + "\n");
  }
}

// ─── TCP Server ────────────────────────────────────────────────────────────

const server = net.createServer((connection) => {
  let buffer = "";

  connection.on("data", (chunk) => {
    buffer += chunk.toString();

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);

      if (!line) continue;

      let request;
      try {
        request = JSON.parse(line);
      } catch {
        writeLine(connection, { type: "error", message: "Invalid JSON" });
        connection.end();
        return;
      }

      processRequest(connection, request);
    }
  });

  connection.on("error", (error) => {
    if (error.code !== "ECONNRESET") {
      log("Connection error:", error.message);
    }
  });
});

async function processRequest(connection, request) {
  const { action } = request;

  try {
    switch (action) {
      case "query":
        await handleQuery(connection, request);
        break;
      case "health":
        handleHealth(connection);
        break;
      default:
        writeLine(connection, { type: "error", message: `Unknown action: ${action}` });
    }
  } catch (error) {
    log(`Error handling ${action}:`, error.message);
    writeLine(connection, { type: "error", message: error.message });
  }

  connection.end();
}

// ─── Start ─────────────────────────────────────────────────────────────────

server.listen(SOCKET_PATH, () => {
  log(`Listening on ${SOCKET_PATH}`);
  log(`Log file: ${LOG_PATH}`);
  process.stdout.write("BRIDGE_READY\n");
});

server.on("error", (error) => {
  log("Server error:", error.message);
  process.exit(1);
});

// ─── Graceful Shutdown ─────────────────────────────────────────────────────

function shutdown() {
  log("Shutting down...");
  server.close();
  if (fs.existsSync(SOCKET_PATH)) fs.unlinkSync(SOCKET_PATH);
  logStream.end();
  process.exit(0);
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
