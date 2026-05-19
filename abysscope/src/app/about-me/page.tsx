import { AboutMeClient } from "@/components/about-me/about-me-client";

export const dynamic = "force-dynamic";

export default function AboutMePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">About Me</h1>
        <p className="text-muted-foreground text-sm">
          모든 봇이 공유하는 사용자 지식 베이스. 봇이 새 사실을 알게 되면{" "}
          <span className="font-medium">propose</span> 상태로 추가하고, 너가 1탭으로
          승인하거나 거부한다.
        </p>
      </div>
      <AboutMeClient />
    </div>
  );
}
