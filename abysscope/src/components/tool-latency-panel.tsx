import type { ToolMetricRow } from "@/lib/abyss";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  rows: ToolMetricRow[];
}

function formatMs(value: number): string {
  if (value === 0) return "0";
  if (value < 1) return value.toFixed(2);
  if (value < 100) return value.toFixed(1);
  return Math.round(value).toString();
}

export function ToolLatencyPanel({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Tool Latency</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No tool calls recorded yet. abyss starts collecting metrics
            after the next PostToolUse hook fires (Phase 4).
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tool Latency</CardTitle>
        <p className="text-xs text-muted-foreground">
          Last 7 days of PostToolUse durations, grouped by tool.
        </p>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="pb-2 font-medium">Tool</th>
                <th className="pb-2 font-medium text-right">Calls</th>
                <th className="pb-2 font-medium text-right">p50 (ms)</th>
                <th className="pb-2 font-medium text-right">p95 (ms)</th>
                <th className="pb-2 font-medium text-right">p99 (ms)</th>
                <th className="pb-2 font-medium text-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.tool} className="border-t">
                  <td className="py-2 font-mono">{row.tool}</td>
                  <td className="py-2 text-right">{row.count}</td>
                  <td className="py-2 text-right">{formatMs(row.p50_ms)}</td>
                  <td className="py-2 text-right">{formatMs(row.p95_ms)}</td>
                  <td className="py-2 text-right">{formatMs(row.p99_ms)}</td>
                  <td className="py-2 text-right">
                    {row.errorCount > 0 ? (
                      <span className="text-destructive font-semibold">
                        {row.errorCount}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
