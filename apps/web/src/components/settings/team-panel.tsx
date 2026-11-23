"use client";

import { UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CopyField } from "@/components/copy-field";
import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ROLE } from "@/lib/labels";
import { useCreateUser, useMe, useUpdateUser, useUsers } from "@/lib/queries";
import type { Role, UserCreated } from "@/lib/types";

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateUser({ silent: true });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [created, setCreated] = useState<UserCreated | null>(null);

  function close(next: boolean) {
    if (!next) {
      setName("");
      setEmail("");
      setRole("viewer");
      setCreated(null);
      create.reset();
    }
    onOpenChange(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setCreated(await create.mutateAsync({ name: name.trim(), email: email.trim(), role }));
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        title={created ? "Account created" : "Add a person"}
        description={
          created
            ? "Give them this one-time password. They should change it after signing in."
            : "They sign in with a one-time password that you hand over yourself."
        }
      >
        {created ? (
          <div className="space-y-4">
            <CopyField value={created.temporary_password} label="One-time password" />
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="Name" htmlFor="invite-name" required>
              <Input id="invite-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </Field>
            <Field label="Email" htmlFor="invite-email" required>
              <Input id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label="Role" htmlFor="invite-role" hint={ROLE[role].description}>
              <NativeSelect id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {(Object.keys(ROLE) as Role[]).map((value) => (
                  <option key={value} value={value}>
                    {ROLE[value].label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {create.error ? <ErrorNotice message={create.error.message} /> : null}
            <DialogFooter>
              <Button variant="secondary" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending}>
                Create account
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function TeamPanel() {
  const me = useMe();
  const users = useUsers();
  const update = useUpdateUser();
  const [inviting, setInviting] = useState(false);

  if (users.error) return <ErrorState message={users.error.message} onRetry={() => users.refetch()} />;
  if (!users.data) return <Skeleton className="h-48" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground max-w-2xl text-[13px]">
          People who can sign in to this dashboard. Clients are separate: they use keys, not accounts.
        </p>
        <Button onClick={() => setInviting(true)}>
          <UserPlus /> Add a person
        </Button>
      </div>
      <TableContainer label="People">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Person</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Last sign-in</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data.items.map((user) => {
              const self = user.id === me.data?.id;
              return (
                <TableRow key={user.id}>
                  <TableCell>
                    <p className="font-medium">
                      {user.name} {self ? <Badge tone="primary">you</Badge> : null}
                    </p>
                    <p className="text-muted-foreground text-[12.5px]">{user.email}</p>
                  </TableCell>
                  <TableCell>
                    <NativeSelect
                      aria-label={`Role of ${user.name}`}
                      value={user.role}
                      disabled={self || update.isPending}
                      className="h-8 w-32 text-[13px]"
                      onChange={(event) => {
                        const role = event.target.value as Role;
                        update.mutate(
                          { id: user.id, role },
                          { onSuccess: () => toast.success(`${user.name} is now ${ROLE[role].label.toLowerCase()}.`) },
                        );
                      }}
                    >
                      {(Object.keys(ROLE) as Role[]).map((value) => (
                        <option key={value} value={value}>
                          {ROLE[value].label}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                  <TableCell>
                    <Badge tone={user.is_active ? "success" : "neutral"}>
                      {user.is_active ? "Active" : "Deactivated"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right">
                    <RelativeTime iso={user.last_login_at} />
                  </TableCell>
                  <TableCell className="text-right">
                    {self ? null : (
                      <Button
                        variant={user.is_active ? "danger-ghost" : "secondary"}
                        size="sm"
                        disabled={update.isPending}
                        onClick={() =>
                          update.mutate(
                            { id: user.id, is_active: !user.is_active },
                            {
                              onSuccess: () =>
                                toast.success(
                                  user.is_active ? `${user.name} was deactivated.` : `${user.name} can sign in again.`,
                                ),
                            },
                          )
                        }
                      >
                        {user.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <InviteDialog open={inviting} onOpenChange={setInviting} />
    </div>
  );
}
