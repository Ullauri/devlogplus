import React, { type ReactElement } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

/**
 * Render helper that wraps the component in a MemoryRouter.
 */
export function renderWithRouter(
  ui: ReactElement,
  { route = "/", ...options }: RenderOptions & { route?: string } = {},
) {
  return render(
    <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>,
    options,
  );
}
