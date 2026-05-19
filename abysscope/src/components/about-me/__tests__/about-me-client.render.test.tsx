// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AboutMeClient } from "../about-me-client";
import type { AboutEntry, AboutMeCategoriesResponse } from "@/lib/abyss-api";

const fetchAboutMeCategoriesMock = vi.fn();
const fetchAboutMeEntriesMock = vi.fn();
const approveAboutMeEntryMock = vi.fn();
const rejectAboutMeEntryMock = vi.fn();
const updateAboutMeEntryMock = vi.fn();

vi.mock("@/lib/abyss-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/abyss-api")>(
    "@/lib/abyss-api",
  );
  return {
    ...actual,
    fetchAboutMeCategories: () => fetchAboutMeCategoriesMock(),
    fetchAboutMeEntries: (cat: string, status?: string) =>
      fetchAboutMeEntriesMock(cat, status),
    approveAboutMeEntry: (cat: string, key: string) =>
      approveAboutMeEntryMock(cat, key),
    rejectAboutMeEntry: (cat: string, key: string) =>
      rejectAboutMeEntryMock(cat, key),
    updateAboutMeEntry: (cat: string, key: string, patch: unknown) =>
      updateAboutMeEntryMock(cat, key, patch),
  };
});

function makeEntry(overrides: Partial<AboutEntry> = {}): AboutEntry {
  return {
    key: "name",
    value: "ash84",
    body: "",
    confidence: "high",
    source: "conversation",
    added: "2026-05-19",
    last_confirmed: "2026-05-19",
    status: "confirmed",
    ...overrides,
  };
}

const summary: AboutMeCategoriesResponse = {
  categories: {
    identity: { confirmed: 1, propose: 1, total: 2 },
    relationships: { confirmed: 0, propose: 0, total: 0 },
    preferences: { confirmed: 0, propose: 0, total: 0 },
    routines: { confirmed: 0, propose: 0, total: 0 },
    current_focus: { confirmed: 0, propose: 0, total: 0 },
    health: { confirmed: 0, propose: 0, total: 0 },
    values: { confirmed: 0, propose: 0, total: 0 },
  },
  pending_proposals: 1,
};

beforeEach(() => {
  fetchAboutMeCategoriesMock.mockReset();
  fetchAboutMeEntriesMock.mockReset();
  approveAboutMeEntryMock.mockReset();
  rejectAboutMeEntryMock.mockReset();
  updateAboutMeEntryMock.mockReset();
  fetchAboutMeCategoriesMock.mockResolvedValue(summary);
  fetchAboutMeEntriesMock.mockResolvedValue([makeEntry()]);
});

describe("AboutMeClient", () => {
  it("renders category overview with pending badge", async () => {
    render(<AboutMeClient />);
    await waitFor(() => {
      expect(screen.getByText("1 proposal pending review")).toBeTruthy();
    });
    expect(screen.getAllByText(/Identity/).length).toBeGreaterThan(0);
    expect(screen.getByText("1 pending")).toBeTruthy();
  });

  it("lists entries for the active category", async () => {
    render(<AboutMeClient />);
    await waitFor(() => {
      expect(screen.getByText("ash84")).toBeTruthy();
    });
  });

  it("approves a propose entry", async () => {
    fetchAboutMeEntriesMock.mockResolvedValueOnce([
      makeEntry({ status: "propose", key: "city", value: "Seoul" }),
    ]);

    render(<AboutMeClient />);
    await waitFor(() => {
      expect(screen.getByLabelText("Approve city")).toBeTruthy();
    });

    fireEvent.click(screen.getByLabelText("Approve city"));
    await waitFor(() => {
      expect(approveAboutMeEntryMock).toHaveBeenCalledWith("identity", "city");
    });
  });

  it("filters by pending status when toggled", async () => {
    render(<AboutMeClient />);
    await waitFor(() => {
      expect(screen.getByText("ash84")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("Pending"));
    await waitFor(() => {
      expect(fetchAboutMeEntriesMock).toHaveBeenLastCalledWith(
        "identity",
        "propose",
      );
    });
  });

  it("switches active category when a tile is clicked", async () => {
    render(<AboutMeClient />);
    await waitFor(() => {
      expect(screen.getByText("ash84")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("Preferences"));
    await waitFor(() => {
      expect(fetchAboutMeEntriesMock).toHaveBeenLastCalledWith(
        "preferences",
        undefined,
      );
    });
  });
});
