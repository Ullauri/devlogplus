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
