module.exports = {
  apps: [
    {
      name: "terrierbot",
      script: "./scripts/pm2-run-terrierbot.sh",
      interpreter: "/bin/bash",
      cwd: ".",
      autorestart: true,
      min_uptime: "10s",
      restart_delay: 5000,
      max_restarts: 100,
      exp_backoff_restart_delay: 100,
      stop_exit_codes: [0],
      env: {
        PYTHON_BIN: "./ven/bin/python",
        BOT_MAIN: "./bot.py",
        ALERT_STATE_FILE: "./data/pm2_restart_state.json",
        PM2_RESTART_WINDOW_SECONDS: "300",
        PM2_RESTART_ALERT_THRESHOLD: "5",
      },
    },
  ],
};
