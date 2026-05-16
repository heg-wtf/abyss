// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SlashCommandList } from "../mobile-chat-slash-command-list";
import type { SlashCommandSpec } from "@/lib/abyss-api";

function spec(name: string, description: string, usage = ""): SlashCommandSpec {
  return { name, description, usage };
}

describe("SlashCommandList", () => {
  it("renders a loading placeholder when the command list is null", () => {
    render(
      <SlashCommandList commands={null} onPick={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("renders an empty-state message when no commands are available", () => {
    render(
      <SlashCommandList commands={[]} onPick={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByText(/no commands available/i)).toBeTruthy();
  });

  it("renders every command and its description", () => {
    const commands = [
      spec("send", "Send a file", "/send filename"),
      spec("ping", "Ping the bot"),
    ];
    render(
      <SlashCommandList
        commands={commands}
        onPick={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("/send")).toBeTruthy();
    expect(screen.getByText("Send a file")).toBeTruthy();
    expect(screen.getByText("/send filename")).toBeTruthy();
    expect(screen.getByText("/ping")).toBeTruthy();
  });

  it("filters by name and description substring (case-insensitive)", () => {
    const commands = [
      spec("send", "Send a file"),
      spec("ping", "Ping the bot"),
      spec("schedule", "Schedule a task"),
    ];
    render(
      <SlashCommandList
        commands={commands}
        onPick={() => {}}
        onClose={() => {}}
      />,
    );
    const search = screen.getByPlaceholderText(/search commands/i);
    fireEvent.change(search, { target: { value: "SCHED" } });
    expect(screen.queryByText("/send")).toBeNull();
    expect(screen.queryByText("/ping")).toBeNull();
    expect(screen.getByText("/schedule")).toBeTruthy();
  });

  it("invokes onPick with the selected command", () => {
    const onPick = vi.fn();
    const cmd = spec("send", "Send a file");
    render(
      <SlashCommandList commands={[cmd]} onPick={onPick} onClose={() => {}} />,
    );
    fireEvent.click(screen.getByText("/send"));
    expect(onPick).toHaveBeenCalledWith(cmd);
  });

  it("invokes onClose when the Close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <SlashCommandList
        commands={[spec("send", "Send a file")]}
        onPick={() => {}}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByText(/^close$/i));
    expect(onClose).toHaveBeenCalled();
  });
});
