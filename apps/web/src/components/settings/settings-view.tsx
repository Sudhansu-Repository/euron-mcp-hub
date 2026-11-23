"use client";

import { AccountPanel } from "@/components/settings/account-panel";
import { ActivityPanel } from "@/components/settings/activity-panel";
import { DeploymentPanel } from "@/components/settings/deployment-panel";
import { TeamPanel } from "@/components/settings/team-panel";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCan } from "@/lib/queries";
import { useUrlParams } from "@/lib/use-url-params";

const TABS = ["account", "team", "activity", "deployment"] as const;
type TabName = (typeof TABS)[number];

export function SettingsView() {
  const isAdmin = useCan("admin");
  const { params, update } = useUrlParams();
  const requested = params.get("tab") as TabName | null;
  const tab: TabName =
    requested && TABS.includes(requested) && (isAdmin || requested !== "team") ? requested : "account";
  return (
    <PageBody>
      <PageHeader
        title="Settings"
        description="Your account, the people who can sign in, and how this deployment is set up."
      />
      <Tabs value={tab} onValueChange={(next) => update({ tab: next === "account" ? null : next })}>
        <TabsList aria-label="Settings sections">
          <TabsTrigger value="account">Account</TabsTrigger>
          {isAdmin ? <TabsTrigger value="team">People</TabsTrigger> : null}
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="deployment">Deployment</TabsTrigger>
        </TabsList>
        <TabsContent value="account">
          <AccountPanel />
        </TabsContent>
        {isAdmin ? (
          <TabsContent value="team">
            <TeamPanel />
          </TabsContent>
        ) : null}
        <TabsContent value="activity">
          <ActivityPanel />
        </TabsContent>
        <TabsContent value="deployment">
          <DeploymentPanel />
        </TabsContent>
      </Tabs>
    </PageBody>
  );
}
