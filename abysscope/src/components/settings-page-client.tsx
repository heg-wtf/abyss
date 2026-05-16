"use client";

import {
  AppearanceSection,
  NotificationsSection,
} from "@/components/settings-dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Client wrapper that mounts the Appearance + Notifications sections
 * inside the (server-rendered) ``/settings`` page. The sections used
 * to live behind a popover the sidebar gear opened — now that the
 * gear is gone, every settings surface lives in this single page.
 */
export function SettingsPageClient() {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Appearance</CardTitle>
        </CardHeader>
        <CardContent>
          <AppearanceSection />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Notifications</CardTitle>
        </CardHeader>
        <CardContent>
          <NotificationsSection />
        </CardContent>
      </Card>
    </>
  );
}
