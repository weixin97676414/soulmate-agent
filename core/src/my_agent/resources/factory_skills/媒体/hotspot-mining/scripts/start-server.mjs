/**
 * Start the DailyHot API server
 * Usage: node scripts/start-server.mjs [port]
 * Default port: 6688
 */
import serveHotApi from "dailyhot-api";

const port = parseInt(process.argv[2]) || 6688;

// Check if port is already in use
async function isPortInUse(p) {
  try {
    const { exec } = await import("child_process");
    return new Promise((resolve) => {
      exec(`netstat -ano | findstr :${p}`, (err) => {
        resolve(!err);
      });
    });
  } catch {
    return false;
  }
}

const inUse = await isPortInUse(port);
if (inUse) {
  console.log(`⚡ DailyHot server already running on port ${port}`);
  process.exit(0);
}

console.log(`🚀 Starting DailyHot API on port ${port}...`);
serveHotApi(port);

// Keep process alive
process.on("SIGINT", () => {
  console.log("\n🛑 Server stopped");
  process.exit(0);
});
