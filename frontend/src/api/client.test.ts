import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, buildQuery } from "./client";

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps the backend data envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ data: { status: "ok" } }),
      }))
    );

    await expect(apiRequest("/health")).resolves.toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:5000/api/v1/health",
      expect.objectContaining({ headers: expect.any(Headers) })
    );
  });

  it("throws ApiError with backend error code and message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({
          error: { code: "validation_error", message: "days must be greater than 0" },
        }),
      }))
    );

    await expect(apiRequest("/market/vix/history?days=0")).rejects.toMatchObject({
      name: "ApiError",
      code: "validation_error",
      message: "days must be greater than 0",
      status: 400,
    });
    await expect(apiRequest("/market/vix/history?days=0")).rejects.toBeInstanceOf(
      ApiError
    );
  });
});

describe("buildQuery", () => {
  it("omits empty values and encodes valid query params", () => {
    expect(
      buildQuery({
        account_id: 1,
        status: "pending",
        empty: "",
        missing: undefined,
        disabled: false,
      })
    ).toBe("?account_id=1&status=pending&disabled=false");
  });
});
