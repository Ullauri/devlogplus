// @ts-check
/**
 * Stryker mutation testing config for DevLog+ frontend.
 *
 * Notes:
 *  - We use the default vitest config (vite.config.ts), NOT
 *    vitest.integration.config.ts — integration tests require a live Prism
 *    mock server and cannot run under Stryker's per-mutant test invocations.
 *  - The generated OpenAPI types (src/api/schema.gen.ts) are never mutated.
 *  - `break: 0` keeps mutation runs non-blocking; they are manual only.
 *
 * Mutation score baseline (April 2026):
 *   Overall ............... 50.99%   (up from 22.53% baseline)
 *   api/client.ts ......... 60.90%
 *   components/
 *     FeedbackControls .... 41.46%   ← not yet improved
 *     Layout .............. 100.00%
 *     SpeechInput ......... 91.18%
 *   pages/
 *     JournalPage ......... 45.31%   ← not yet improved
 *     OnboardingPage ...... 82.68%
 *     ProfilePage ......... 54.55%   ← not yet improved
 *     ProjectsPage ........ 85.00%
 *     QuizPage ............ 83.33%
 *     ReadingsPage ........ 44.19%   ← not yet improved
 *     SettingsPage ........ 37.30%   ← 1121-line file; needs more work
 *     TriagePage .......... 46.67%   ← not yet improved
 *
 * Once remaining files are raised above ~60%, consider setting
 * `break` to a non-zero value (e.g., 45) to prevent regressions.
 */

/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
const config = {
  packageManager: "npm",
  testRunner: "vitest",
  vitest: {
    configFile: "vite.config.ts",
  },
  coverageAnalysis: "perTest",

  mutate: [
    "src/api/client.ts",
    "src/components/**/*.tsx",
    "src/pages/**/*.tsx",
    // Explicit exclusions (negative globs)
    "!src/api/schema.gen.ts",
    "!src/**/*.test.ts",
    "!src/**/*.test.tsx",
    "!src/test/**/*",
  ],

  reporters: ["html", "clear-text", "progress"],
  htmlReporter: {
    fileName: "reports/mutation/index.html",
  },

  thresholds: {
    high: 80,
    low: 60,
    break: 0,
  },
};

export default config;
