"use client";

import { useState } from "react";

interface BotAvatarProps {
  botName: string;
  displayName: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASSES = {
  sm: "w-8 h-8 text-sm",
  md: "w-12 h-12 text-base",
  lg: "w-16 h-16 text-xl",
};

const FALLBACK_COLORS = [
  "bg-blue-500",
  "bg-purple-500",
  "bg-green-500",
  "bg-orange-500",
  "bg-pink-500",
  "bg-teal-500",
  "bg-red-500",
  "bg-indigo-500",
];

function getFallbackColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
}

export function BotAvatar({
  botName,
  displayName,
  size = "md",
  className = "",
}: BotAvatarProps) {
  const [hasError, setHasError] = useState(false);
  const sizeClass = SIZE_CLASSES[size];
  const fallbackColor = getFallbackColor(botName);
  const initial = (displayName || botName).charAt(0).toUpperCase();

  if (hasError) {
    return (
      <div
        className={`${sizeClass} ${fallbackColor} rounded-xl flex items-center justify-center text-white font-semibold flex-shrink-0 ${className}`}
      >
        {initial}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/api/bots/${botName}/avatar`}
      alt={displayName || botName}
      className={`${sizeClass} rounded-xl object-cover flex-shrink-0 ${className}`}
      onError={() => setHasError(true)}
    />
  );
}
