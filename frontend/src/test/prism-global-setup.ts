/**
 * Vitest globalSetup for integration tests.
 *
 * Starts a Prism mock server before all tests and tears it down after.
 * The mock server reads the OpenAPI spec from docs/openapi.json — the
 * single source of truth for the API contract.
 */

import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SPEC_PATH = path.resolve(__dirname, "../../../docs/openapi.json");
const PRISM_PORT = 4010;
const PRISM_HOST = "0.0.0.0";

let prismProcess: ChildProcess | null = null;

/**
 * Wait until `http://host:port` responds, with a timeout.
 */
async function waitForServer(
  host: string,
  port: number,
  timeoutMs = 20_000,
): Promise<void> {
  const url = `http://${host === "0.0.0.0" ? "127.0.0.1" : host}:${port}/`;
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    try {
      await fetch(url);
      return; // server is up
    } catch {
      await new Promise((r) => setTimeout(r, 250));
    }
  }

  throw new Error(`Prism did not start within ${timeoutMs}ms`);
}

export async function setup(): Promise<void> {
  // Resolve the prism binary from node_modules
  const prismBin = path.resolve(__dirname, "../../node_modules/.bin/prism");

  console.log(`\n🔶 Starting Prism mock server on port ${PRISM_PORT}…`);
  console.log(`   Spec: ${SPEC_PATH}`);

  prismProcess = spawn(
    prismBin,
    [
      "mock",
      SPEC_PATH,
      "--host",
      PRISM_HOST,
      "--port",
      String(PRISM_PORT),
      "--dynamic",
    ],
    {
      stdio: ["ignore", "pipe", "pipe"],
      detached: false,
    },
  );

  // Forward Prism stderr to console for debugging failures
  prismProcess.stderr?.on("data", (chunk: Buffer) => {
    const msg = chunk.toString().trim();
    if (msg) console.error(`   [prism] ${msg}`);
  });

  prismProcess.on("error", (err) => {
    console.error("Failed to start Prism:", err);
  });

  await waitForServer(PRISM_HOST, PRISM_PORT);
  console.log(`✅ Prism mock server ready on http://127.0.0.1:${PRISM_PORT}\n`);
}

export async function teardown(): Promise<void> {
  if (prismProcess && !prismProcess.killed) {
    console.log("\n🔶 Stopping Prism mock server…");
    prismProcess.kill("SIGTERM");

    // Give it a moment to shut down gracefully
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        prismProcess?.kill("SIGKILL");
        resolve();
      }, 3_000);
      prismProcess?.on("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
    });
    console.log("✅ Prism stopped.\n");
  }
}
