import fs from "fs";
import yaml from "js-yaml";

export function readYaml<T>(filePath: string): T | null {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    return yaml.load(content) as T;
  } catch {
    return null;
  }
}

export function writeYaml(filePath: string, data: unknown): void {
  const content = yaml.dump(data, {
    lineWidth: 100,
    noRefs: true,
    quotingType: "'",
    forceQuotes: false,
  });
  fs.writeFileSync(filePath, content, "utf-8");
}

export function readMarkdown(filePath: string): string {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return "";
  }
}

export function writeMarkdown(filePath: string, content: string): void {
  fs.writeFileSync(filePath, content, "utf-8");
}
