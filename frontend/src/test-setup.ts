import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

const testGlobal = globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT?: boolean;
};

testGlobal.IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => cleanup());
