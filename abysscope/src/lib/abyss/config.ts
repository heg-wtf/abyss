import { abyssPath } from "./paths";
import { readYaml, writeYaml } from "./io";

export interface GlobalConfig {
  bots: { name: string; path: string }[];
  timezone: string;
  language: string;
  settings: {
    command_timeout: number;
    log_level: string;
  };
}

export function getConfig(): GlobalConfig | null {
  return readYaml<GlobalConfig>(abyssPath("config.yaml"));
}

export function updateConfig(config: GlobalConfig): void {
  writeYaml(abyssPath("config.yaml"), config);
}
