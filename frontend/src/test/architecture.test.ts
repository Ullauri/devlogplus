/**
 * Architecture tests for DevLog+ frontend using ArchUnitTS.
 *
 * These tests enforce layered dependency boundaries between source
 * directories using proper TypeScript AST analysis — the frontend
 * equivalent of the backend's pytestarch tests.
 *
 * Layers (allowed direction →):
 *
 *   main.tsx    → App
 *   App.tsx     → pages, components, api
 *   pages/*     → api, components  (never other pages, App, or main)
 *   components/*→ api              (never pages, App, or main)
 *   api/*       → (nothing local — pure leaf)
 */

import { projectFiles } from "archunit";
import { describe, it, expect } from "vitest";

// ═════════════════════════════════════════════════════════════════════════════
// 1. API — pure leaf: no dependencies on any other layer
// ═════════════════════════════════════════════════════════════════════════════
describe("Architecture: api/ is a leaf layer", () => {
  it("should not depend on components", async () => {
    const rule = projectFiles()
      .inFolder("src/api/**")
      .shouldNot()
      .dependOnFiles()
      .inFolder("src/components/**");
    await expect(rule).toPassAsync();
  });

  it("should not depend on pages", async () => {
    const rule = projectFiles()
      .inFolder("src/api/**")
      .shouldNot()
      .dependOnFiles()
      .inFolder("src/pages/**");
    await expect(rule).toPassAsync();
  });

  it("should not depend on App.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/api/**")
      .shouldNot()
      .dependOnFiles()
      .withName("App.tsx");
    await expect(rule).toPassAsync();
  });

  it("should not depend on main.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/api/**")
      .shouldNot()
      .dependOnFiles()
      .withName("main.tsx");
    await expect(rule).toPassAsync();
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// 2. COMPONENTS — may depend on api, never on pages/App/main
// ═════════════════════════════════════════════════════════════════════════════
describe("Architecture: components/ never import from pages, App, or main", () => {
  it("should not depend on pages", async () => {
    const rule = projectFiles()
      .inFolder("src/components/**")
      .shouldNot()
      .dependOnFiles()
      .inFolder("src/pages/**");
    await expect(rule).toPassAsync();
  });

  it("should not depend on App.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/components/**")
      .shouldNot()
      .dependOnFiles()
      .withName("App.tsx");
    await expect(rule).toPassAsync();
  });

  it("should not depend on main.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/components/**")
      .shouldNot()
      .dependOnFiles()
      .withName("main.tsx");
    await expect(rule).toPassAsync();
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// 3. PAGES — may depend on api + components, never on App/main/other pages
// ═════════════════════════════════════════════════════════════════════════════
describe("Architecture: pages/ never import from App, main, or other pages", () => {
  it("should not depend on App.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/pages/**")
      .shouldNot()
      .dependOnFiles()
      .withName("App.tsx");
    await expect(rule).toPassAsync();
  });

  it("should not depend on main.tsx", async () => {
    const rule = projectFiles()
      .inFolder("src/pages/**")
      .shouldNot()
      .dependOnFiles()
      .withName("main.tsx");
    await expect(rule).toPassAsync();
  });

  it("should not import from other pages", async () => {
    // Use .check() to manually filter out self-references and test→source
    // imports (co-located test files naturally import their own page).
    const rule = projectFiles()
      .inFolder("src/pages/**")
      .withName(/^(?!.*\.test\.).*\.tsx$/)
      .shouldNot()
      .dependOnFiles()
      .inFolder("src/pages/**");

    const violations = await rule.check();
    const real = violations.filter((v) => {
      // Exclude self-references (ArchUnitTS reports file → same file)
      const dep = v as {
        dependency?: { sourceLabel: string; targetLabel: string };
      };
      if (dep.dependency) {
        return dep.dependency.sourceLabel !== dep.dependency.targetLabel;
      }
      return true;
    });
    expect(real).toEqual([]);
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// 4. NO UPWARD DEPENDENCIES — App ↛ main, no cycles
// ═════════════════════════════════════════════════════════════════════════════
describe("Architecture: no upward dependencies (cycle prevention)", () => {
  it("App.tsx should not depend on main.tsx", async () => {
    const rule = projectFiles()
      .withName("App.tsx")
      .shouldNot()
      .dependOnFiles()
      .withName("main.tsx");
    await expect(rule).toPassAsync();
  });

  it("src/ should be free of circular dependencies", async () => {
    const rule = projectFiles().inFolder("src/**").should().haveNoCycles();
    await expect(rule).toPassAsync();
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// 5. API CLIENT CONTRACT — no hand-rolled request/response types
// ═════════════════════════════════════════════════════════════════════════════
// client.ts MUST source its types from schema.gen.ts (which is generated
// from docs/openapi.json). Hand-rolled types are how client↔spec drift
// creeps in (see the 2026-04 onboarding/complete 422 postmortem).
describe("Architecture: api/client.ts uses generated OpenAPI types", () => {
  it("client.ts imports the generated schema module", async () => {
    const fs = await import("node:fs/promises");
    const src = await fs.readFile("src/api/client.ts", "utf8");
    expect(src).toMatch(/from ["']\.\/schema\.gen["']/);
  });

  it("client.ts does not use `any` in exported API signatures", async () => {
    const fs = await import("node:fs/promises");
    const src = await fs.readFile("src/api/client.ts", "utf8");
    // Allow `any` in comments but not in code.
    const withoutComments = src
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    expect(withoutComments).not.toMatch(/:\s*any\b/);
  });

  it("schema.gen.ts exists and declares components", async () => {
    const fs = await import("node:fs/promises");
    const src = await fs.readFile("src/api/schema.gen.ts", "utf8");
    expect(src).toMatch(/export interface components/);
  });
});
