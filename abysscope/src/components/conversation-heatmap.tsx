import type { BotConversationFrequency } from "@/lib/abyss";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKS = 52;

function getColorClass(count: number): string {
  if (count === 0) return "bg-muted";
  if (count <= 2) return "bg-emerald-200 dark:bg-emerald-900";
  if (count <= 5) return "bg-emerald-400 dark:bg-emerald-700";
  if (count <= 10) return "bg-emerald-600 dark:bg-emerald-500";
  return "bg-emerald-800 dark:bg-emerald-300";
}

function buildGrid(data: Record<string, number>): { date: string; count: number }[][] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Start from Sunday of the week 52 weeks ago
  const start = new Date(today);
  start.setDate(start.getDate() - WEEKS * 7 - start.getDay());

  const columns: { date: string; count: number }[][] = [];

  for (let week = 0; week <= WEEKS; week++) {
    const col: { date: string; count: number }[] = [];
    for (let dow = 0; dow < 7; dow++) {
      const d = new Date(start);
      d.setDate(start.getDate() + week * 7 + dow);
      if (d > today) {
        col.push({ date: "", count: 0 });
        continue;
      }
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      col.push({ date: iso, count: data[iso] || 0 });
    }
    columns.push(col);
  }

  return columns;
}

function getMonthLabels(columns: { date: string; count: number }[][]): { label: string; col: number }[] {
  const labels: { label: string; col: number }[] = [];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  let lastMonth = -1;

  for (let i = 0; i < columns.length; i++) {
    const firstDate = columns[i].find((c) => c.date)?.date;
    if (!firstDate) continue;
    const month = parseInt(firstDate.slice(5, 7), 10) - 1;
    if (month !== lastMonth) {
      labels.push({ label: months[month], col: i });
      lastMonth = month;
    }
  }

  return labels;
}

interface Props {
  bot: BotConversationFrequency;
}

export function ConversationHeatmap({ bot }: Props) {
  const columns = buildGrid(bot.data);
  const monthLabels = getMonthLabels(columns);

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium">{bot.displayName}</span>
        <span className="text-xs text-muted-foreground">{bot.total} conversations</span>
      </div>
      <div className="overflow-x-auto">
        <div className="inline-flex flex-col gap-1 min-w-max">
          {/* Month labels */}
          <div className="flex gap-[3px] ml-8">
            {columns.map((_, i) => {
              const label = monthLabels.find((m) => m.col === i);
              return (
                <div key={i} className="w-[11px] text-[9px] text-muted-foreground">
                  {label?.label ?? ""}
                </div>
              );
            })}
          </div>
          {/* Grid rows (Sun–Sat) */}
          {DAYS.map((day, dow) => (
            <div key={day} className="flex items-center gap-1">
              <span className="text-[9px] text-muted-foreground w-7 text-right leading-none">
                {dow % 2 === 1 ? day : ""}
              </span>
              <div className="flex gap-[3px]">
                {columns.map((col, week) => {
                  const cell = col[dow];
                  return (
                    <div
                      key={week}
                      className={`w-[11px] h-[11px] rounded-sm ${getColorClass(cell.count)}`}
                      title={cell.date ? `${cell.date}: ${cell.count}` : ""}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
