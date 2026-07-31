#!/usr/bin/env node
/**
 * Thin launcher: resolve plugin Python runtime and exec hook_entry.py.
 * Keeps hooks.json on node (widely available) while logic stays in Python.
 *
 * Env (optional overrides):
 *   TOKENSENTINEL_PYTHON  — absolute path to python interpreter
 *   TOKENSENTINEL_MODE    — observe | alert | strict
 *   TOKENSENTINEL_PROJECT
 *   TOKENSENTINEL_CLOUD_ENDPOINT
 *   TOKENSENTINEL_API_KEY
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.resolve(__dirname, "..");
const dataDir =
  process.env.CLAUDE_PLUGIN_DATA ||
  path.join(os.homedir(), ".claude", "plugins", "data", "tokensentinel-tokensentinel");
const hostEvent = process.argv[2] || "PostToolUse";

function findPython() {
  if (process.env.TOKENSENTINEL_PYTHON && fs.existsSync(process.env.TOKENSENTINEL_PYTHON)) {
    return process.env.TOKENSENTINEL_PYTHON;
  }
  const venvUnix = path.join(dataDir, "venv", "bin", "python");
  const venvWin = path.join(dataDir, "venv", "Scripts", "python.exe");
  if (fs.existsSync(venvUnix)) return venvUnix;
  if (fs.existsSync(venvWin)) return venvWin;
  // Fall back to PATH
  for (const name of ["python3", "python"]) {
    const r = spawnSync(name, ["-c", "import sys; print(sys.executable)"], {
      encoding: "utf8",
    });
    if (r.status === 0 && r.stdout.trim()) return r.stdout.trim();
  }
  return null;
}

function ensureRuntime(python) {
  const marker = path.join(dataDir, "runtime.ok");
  const req = path.join(pluginRoot, "requirements.txt");
  if (fs.existsSync(marker) && fs.existsSync(req)) {
    // Reinstall if requirements.txt changed
    try {
      const want = fs.readFileSync(req, "utf8");
      const got = fs.existsSync(path.join(dataDir, "requirements.sha"))
        ? fs.readFileSync(path.join(dataDir, "requirements.sha"), "utf8")
        : "";
      if (want === got) return true;
    } catch (_) {
      /* continue */
    }
  }
  fs.mkdirSync(dataDir, { recursive: true });
  const venvDir = path.join(dataDir, "venv");
  if (!fs.existsSync(path.join(venvDir, "bin", "python")) && !fs.existsSync(path.join(venvDir, "Scripts", "python.exe"))) {
    const cr = spawnSync(python, ["-m", "venv", venvDir], { encoding: "utf8" });
    if (cr.status !== 0) {
      process.stderr.write(cr.stderr || "venv create failed\n");
      return false;
    }
  }
  const py = fs.existsSync(path.join(venvDir, "bin", "python"))
    ? path.join(venvDir, "bin", "python")
    : path.join(venvDir, "Scripts", "python.exe");
  // Prefer sibling source checkouts when developing next to sdk/adapter; else PyPI.
  const sdk = path.resolve(pluginRoot, "..", "tokensentinel-sdk-python");
  const adapter = path.resolve(pluginRoot, "..", "tokensentinel-adapter");
  const installs = [];
  if (fs.existsSync(path.join(sdk, "pyproject.toml"))) {
    installs.push(["-m", "pip", "install", "-q", "-e", sdk]);
  }
  if (fs.existsSync(path.join(adapter, "pyproject.toml"))) {
    installs.push(["-m", "pip", "install", "-q", "-e", adapter]);
  }
  if (fs.existsSync(req)) {
    installs.push(["-m", "pip", "install", "-q", "-r", req]);
  }
  // Always ensure this package path is importable
  installs.push(["-m", "pip", "install", "-q", "-e", pluginRoot]);

  for (const args of installs) {
    const r = spawnSync(py, args, { encoding: "utf8", env: process.env });
    if (r.status !== 0) {
      process.stderr.write(r.stderr || `pip failed: ${args.join(" ")}\n`);
      // Non-fatal for SessionStart messaging; hook_entry will fail-open
    }
  }
  try {
    if (fs.existsSync(req)) {
      fs.writeFileSync(path.join(dataDir, "requirements.sha"), fs.readFileSync(req, "utf8"));
    }
    fs.writeFileSync(marker, new Date().toISOString());
  } catch (_) {
    /* ignore */
  }
  return true;
}

const basePython = findPython();
if (!basePython) {
  // Fail-open: no python → exit 0, no JSON (Claude continues)
  process.exit(0);
}

if (hostEvent === "SessionStart") {
  ensureRuntime(basePython);
}

const py =
  (fs.existsSync(path.join(dataDir, "venv", "bin", "python")) &&
    path.join(dataDir, "venv", "bin", "python")) ||
  (fs.existsSync(path.join(dataDir, "venv", "Scripts", "python.exe")) &&
    path.join(dataDir, "venv", "Scripts", "python.exe")) ||
  basePython;

const entry = path.join(pluginRoot, "scripts", "hook_entry.py");
const r = spawnSync(py, [entry, hostEvent], {
  input: fs.readFileSync(0), // stdin from Claude Code
  encoding: "utf8",
  env: {
    ...process.env,
    CLAUDE_PLUGIN_ROOT: pluginRoot,
    CLAUDE_PLUGIN_DATA: dataDir,
    PYTHONPATH: [pluginRoot, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
  },
  maxBuffer: 10 * 1024 * 1024,
});

if (r.stdout) process.stdout.write(r.stdout);
if (r.stderr) process.stderr.write(r.stderr);
// Always exit 0 for fail-open unless Python returned intentional non-zero with deny JSON already on stdout
process.exit(0);
