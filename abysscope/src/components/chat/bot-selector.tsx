"use client";

import * as React from "react";
import { Bot } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { BotSummary } from "@/lib/abyss-api";

interface Props {
  bots: BotSummary[];
  value: string | null;
  onChange: (botName: string) => void;
  disabled?: boolean;
}

export function BotSelector({ bots, value, onChange, disabled }: Props) {
  return (
    <Select
      value={value ?? undefined}
      onValueChange={(next) => {
        if (next) onChange(next);
      }}
      disabled={disabled || bots.length === 0}
    >
      <SelectTrigger className="w-[260px]">
        <Bot className="size-4 text-muted-foreground" />
        <SelectValue placeholder="Pick a bot to chat with" />
      </SelectTrigger>
      <SelectContent>
        {bots.map((bot) => (
          <SelectItem key={bot.name} value={bot.name}>
            <div className="flex flex-col items-start">
              <span className="font-medium">{bot.display_name}</span>
              <span className="text-xs text-muted-foreground">{bot.type}</span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
