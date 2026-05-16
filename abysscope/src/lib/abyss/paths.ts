import path from "path";

export function getAbyssHome(): string {
  return process.env.ABYSS_HOME || path.join(process.env.HOME || "~", ".abyss");
}

export function abyssPath(...segments: string[]): string {
  return path.join(getAbyssHome(), ...segments);
}
