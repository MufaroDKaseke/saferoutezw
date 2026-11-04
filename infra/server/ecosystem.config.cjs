// pm2 process definitions for the production server. Paths are absolute on purpose: they match the
// layout created by infra/server/bootstrap.sh and the venv created by deploy.sh.
//
//   pm2 startOrReload infra/server/ecosystem.config.cjs --update-env
const fs = require("fs");
const path = require("path");

const ROOT = "/opt/saferoutezw";
const APP = `${ROOT}/app`;
const PYTHON = `${ROOT}/venv/bin/python`;

// KEY=VALUE lines of web.env (comments and blank lines ignored).
function readEnvFile(file) {
  const env = {};
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (match) env[match[1]] = match[2];
  }
  return env;
}

const common = {
  autorestart: true,
  time: true, // timestamp every log line
  kill_timeout: 10000,
};

module.exports = {
  apps: [
    {
      ...common,
      name: "saferoute-api",
      cwd: `${APP}/apps/api`,
      script: PYTHON,
      args: "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1",
      interpreter: "none",
      env: { PYTHONUNBUFFERED: "1" },
      max_memory_restart: "400M",
    },
    {
      ...common,
      name: "saferoute-web",
      cwd: `${APP}/apps/web`,
      script: "node_modules/next/dist/bin/next",
      args: "start --hostname 127.0.0.1 --port 3000",
      env: {
        ...readEnvFile(path.join(__dirname, "web.env")),
        NODE_ENV: "production",
        NODE_OPTIONS: "--max-old-space-size=512",
      },
      max_memory_restart: "700M",
    },
    {
      // RSS polling, the article pipeline, social ingestion and the WhatsApp dispatcher. Separate from
      // the API on purpose (see apps/api/app/jobs/scheduler.py). RSS_SCHEDULER_ENABLED=false in the
      // server's .env makes it exit 0, which pm2 must not treat as a crash.
      ...common,
      name: "saferoute-scheduler",
      cwd: `${APP}/apps/api`,
      script: PYTHON,
      args: "-m app.jobs.scheduler",
      interpreter: "none",
      env: { PYTHONUNBUFFERED: "1" },
      stop_exit_codes: [0],
      restart_delay: 5000,
      max_memory_restart: "400M",
    },
  ],
};
