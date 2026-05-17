"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * Controlled form that submits to ``POST /api/bots/new``.
 *
 * Field rules mirror the CLI flow (``onboarding.prompt_bot_profile``):
 *   - ``name``: required, lowercased + spaces → hyphens client-side
 *     so the user sees the eventual directory name as they type
 *   - ``display_name``, ``personality``, ``role``: required
 *   - ``goal``: optional (matches ``create_bot`` defaulting to "")
 *
 * Server-side re-validates everything; we only do client-side
 * normalization for UX.
 */

interface FieldErrors {
  name?: string;
  display_name?: string;
  personality?: string;
  role?: string;
  form?: string;
}

const NAME_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;

export function NewBotForm() {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [alias, setAlias] = React.useState("");
  const [personality, setPersonality] = React.useState("");
  const [role, setRole] = React.useState("");
  const [goal, setGoal] = React.useState("");
  const [errors, setErrors] = React.useState<FieldErrors>({});
  const [submitting, setSubmitting] = React.useState(false);

  const normalizeName = (value: string) =>
    value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

  const validate = (): FieldErrors => {
    const next: FieldErrors = {};
    if (!name.trim()) next.name = "Required.";
    else if (!NAME_PATTERN.test(name))
      next.name = "Lowercase letters, digits, and hyphens only (1-64 chars).";
    if (!displayName.trim()) next.display_name = "Required.";
    if (!personality.trim()) next.personality = "Required.";
    if (!role.trim()) next.role = "Required.";
    return next;
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const response = await fetch("/api/bots/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          display_name: displayName,
          alias: alias.trim(),
          personality,
          role,
          goal,
        }),
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as {
          error?: string;
        };
        setErrors({
          form: detail.error || `Failed (${response.status}).`,
        });
        return;
      }
      router.push(`/bots/${encodeURIComponent(name)}`);
      router.refresh();
    } catch (caught) {
      setErrors({
        form:
          caught instanceof Error ? caught.message : "Network error.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="bot-name">
          Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="bot-name"
          value={name}
          onChange={(event) => setName(normalizeName(event.target.value))}
          placeholder="my-helper"
          aria-invalid={!!errors.name}
          autoFocus
        />
        <p className="text-xs text-muted-foreground">
          Used as the directory name under{" "}
          <code className="font-mono">~/.abyss/bots/</code>. Lowercase
          letters, digits, hyphens.
        </p>
        {errors.name && (
          <p className="text-xs text-destructive">{errors.name}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="bot-display-name">
          Display name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="bot-display-name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="The friendly name shown in chat headers"
          aria-invalid={!!errors.display_name}
        />
        {errors.display_name && (
          <p className="text-xs text-destructive">{errors.display_name}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="bot-alias">Alias (optional)</Label>
        <Input
          id="bot-alias"
          value={alias}
          maxLength={30}
          onChange={(event) => setAlias(event.target.value)}
          placeholder="e.g. 집사 — shown as '앤 (집사)' in lists"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="bot-personality">
          Personality <span className="text-destructive">*</span>
        </Label>
        <Textarea
          id="bot-personality"
          value={personality}
          onChange={(event) => setPersonality(event.target.value)}
          rows={5}
          placeholder={
            "Background, tone, quirks. Anything the bot should keep in mind about itself."
          }
          aria-invalid={!!errors.personality}
        />
        {errors.personality && (
          <p className="text-xs text-destructive">{errors.personality}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="bot-role">
          Role <span className="text-destructive">*</span>
        </Label>
        <Textarea
          id="bot-role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          rows={4}
          placeholder="What it does, what it should never do, what tools it favours."
          aria-invalid={!!errors.role}
        />
        {errors.role && (
          <p className="text-xs text-destructive">{errors.role}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="bot-goal">Goal</Label>
        <Textarea
          id="bot-goal"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={3}
          placeholder="Optional — the long-arc objective. Helps the bot prioritise."
        />
      </div>

      {errors.form && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errors.form}
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push("/")}
          disabled={submitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {submitting ? "Creating…" : "Create bot"}
        </Button>
      </div>
    </form>
  );
}
