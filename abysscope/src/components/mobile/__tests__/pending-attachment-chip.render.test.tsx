// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PendingAttachmentChip } from "../mobile-chat-attachment-chip";
import type { PendingAttachment } from "../mobile-chat-types";

function makeAttachment(
  overrides: Partial<PendingAttachment> = {},
): PendingAttachment {
  return {
    localId: "a-1",
    file: new File(["x"], "photo.jpg", { type: "image/jpeg" }),
    uploading: false,
    ...overrides,
  };
}

describe("PendingAttachmentChip", () => {
  it("shows the file name", () => {
    render(
      <PendingAttachmentChip
        attachment={makeAttachment()}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText("photo.jpg")).toBeTruthy();
  });

  it("renders an in-progress ellipsis while uploading", () => {
    render(
      <PendingAttachmentChip
        attachment={makeAttachment({ uploading: true })}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText("…")).toBeTruthy();
  });

  it("renders the destructive marker when upload errored", () => {
    const { container } = render(
      <PendingAttachmentChip
        attachment={makeAttachment({ error: "too large" })}
        onRemove={() => {}}
      />,
    );
    expect(container.querySelector(".text-destructive")).not.toBeNull();
  });

  it("invokes onRemove when the remove button is clicked", () => {
    const onRemove = vi.fn();
    render(
      <PendingAttachmentChip
        attachment={makeAttachment()}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByLabelText(/remove attachment/i));
    expect(onRemove).toHaveBeenCalled();
  });
});
