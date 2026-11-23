"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { PasswordForm } from "@/components/shell/password-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/input";
import { ROLE } from "@/lib/labels";
import { useMe, useUpdateProfile } from "@/lib/queries";

export function AccountPanel() {
  const me = useMe();
  const update = useUpdateProfile({ silent: true });
  const [name, setName] = useState(me.data?.name ?? "");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync(name.trim());
    } catch {
      return;
    }
    toast.success("Profile updated.");
  }

  if (!me.data) return null;
  return (
    <div className="grid max-w-4xl gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Profile</CardTitle>
            <CardDescription>
              Signed in as {me.data.email}, with the {ROLE[me.data.role].label.toLowerCase()} role:{" "}
              {ROLE[me.data.role].description.toLowerCase()}
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <Field label="Name" htmlFor="profile-name" required>
              <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
            {update.error ? <ErrorNotice message={update.error.message} /> : null}
            <Button type="submit" loading={update.isPending} disabled={name.trim() === me.data.name}>
              Save
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Password</CardTitle>
            <CardDescription>Changing it signs you out everywhere else.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <PasswordForm idPrefix="settings-password" />
        </CardContent>
      </Card>
    </div>
  );
}
