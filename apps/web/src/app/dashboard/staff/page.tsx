"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import {
  History,
  MousePointerClick,
  ChefHat,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";

import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import IconButton from "@/components/ui/IconButton";
import Input from "@/components/ui/Input";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import SearchInput from "@/components/ui/SearchInput";
import { EmptyState, Skeleton, Spinner } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";

type StaffMember = {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
};

type Permission = {
  id: number;
  action: "CREATE" | "READ" | "UPDATE";
  permission_code: string;
  // Whether an ADMIN may assign this permission to a STAFF user.
  assignable: boolean;
};

type PermissionModule = {
  id: number;
  name: string;
  code: string;
  permissions: Permission[];
};

type AssignedPermission = {
  id: number;
  permission_code: string;
  action: string;
  module_id: number;
  module_name: string;
  module_code: string;
  assignable: boolean;
  /** False for a kept assignment STAFF can never use (purchase orders are
   * Admin and Kitchen Manager only). */
  effective?: boolean;
};

type StaffDetail = {
  staff: StaffMember;
  permissions: AssignedPermission[];
};

const ACTION_ORDER = ["READ", "CREATE", "UPDATE"] as const;

const ACTION_LABELS: Record<string, string> = {
  READ: "View",
  CREATE: "Create",
  UPDATE: "Edit",
};

function getErrorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

function sameIds(a: number[], b: number[]) {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((id) => set.has(id));
}

export default function StaffManagementPage() {
  const toast = useToast();

  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [modules, setModules] = useState<PermissionModule[]>([]);
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [selectedPermissionIds, setSelectedPermissionIds] = useState<number[]>([]);
  // What the server last reported, so unsaved edits can be detected.
  const [savedPermissionIds, setSavedPermissionIds] = useState<number[]>([]);
  // Older permissions that can no longer be assigned to staff. They are
  // shown for information and kept unchanged when saving.
  const [keptPermissions, setKeptPermissions] = useState<AssignedPermission[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [pendingSwitch, setPendingSwitch] = useState<StaffMember | null>(null);

  const [query, setQuery] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [createError, setCreateError] = useState("");
  // Which account type the Add form creates (27 Nov 2026: Admins add both).
  const [createRole, setCreateRole] = useState<"STAFF" | "KITCHEN_MANAGER">("STAFF");

  const selectedStaff = useMemo(
    () => staff.find((member) => member.id === selectedStaffId) ?? null,
    [staff, selectedStaffId]
  );

  // Only permissions that may be assigned to staff are offered.
  const assignableModules = useMemo(
    () =>
      modules
        .map((module) => ({
          ...module,
          permissions: module.permissions.filter(
            (permission) => permission.assignable
          ),
        }))
        .filter((module) => module.permissions.length > 0),
    [modules]
  );

  const matrixActions = useMemo(() => {
    const present = new Set(
      assignableModules.flatMap((module) =>
        module.permissions.map((permission) => permission.action)
      )
    );
    return ACTION_ORDER.filter((action) => present.has(action));
  }, [assignableModules]);

  const assignableCount = assignableModules.reduce(
    (total, module) => total + module.permissions.length,
    0
  );

  const dirty =
    selectedStaff !== null &&
    !sameIds(selectedPermissionIds, savedPermissionIds);

  const visibleStaff = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return staff;
    return staff.filter((member) =>
      `${member.full_name} ${member.email}`.toLowerCase().includes(needle)
    );
  }, [staff, query]);

  const applyStaffDetail = (detail: StaffDetail) => {
    const assigned = detail.permissions
      .filter((permission) => permission.assignable)
      .map((permission) => permission.id);

    setSelectedPermissionIds(assigned);
    setSavedPermissionIds(assigned);
    setKeptPermissions(
      detail.permissions.filter((permission) => !permission.assignable)
    );
  };

  // State is set only in promise callbacks, so this is safe in an effect.
  const fetchData = useCallback(() => {
    return Promise.all([
      api.get<StaffMember[]>(ENDPOINTS.staff),
      api.get<PermissionModule[]>(ENDPOINTS.authorizationModules),
    ])
      .then(([staffResult, modulesResult]) => {
        setStaff(staffResult);
        setModules(modulesResult);
        setError("");
      })
      .catch((err: unknown) => {
        setError(getErrorMessage(err));
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const loadData = () => {
    setRefreshing(true);
    return fetchData();
  };

  const selectStaff = async (member: StaffMember) => {
    setSelectedStaffId(member.id);
    setDetailLoading(true);
    setError("");

    try {
      const detail = await api.get<StaffDetail>(
        `${ENDPOINTS.staff}/${member.id}`
      );

      applyStaffDetail(detail);
    } catch (err) {
      setSelectedPermissionIds([]);
      setSavedPermissionIds([]);
      setKeptPermissions([]);
      setError(getErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  /** Asks before discarding unsaved permission edits. */
  const requestSelect = (member: StaffMember) => {
    if (member.id === selectedStaffId) return;
    if (dirty) {
      setPendingSwitch(member);
      return;
    }
    void selectStaff(member);
  };

  const togglePermission = (permissionId: number) => {
    setSelectedPermissionIds((current) =>
      current.includes(permissionId)
        ? current.filter((id) => id !== permissionId)
        : [...current, permissionId]
    );
  };

  /** Turns every permission in a module on, or off if all are on. */
  const toggleModule = (module: PermissionModule) => {
    const ids = module.permissions.map((permission) => permission.id);

    setSelectedPermissionIds((current) => {
      const allOn = ids.every((id) => current.includes(id));
      return allOn
        ? current.filter((id) => !ids.includes(id))
        : [...new Set([...current, ...ids])];
    });
  };

  const openCreateForm = (role: "STAFF" | "KITCHEN_MANAGER" = "STAFF") => {
    setCreateRole(role);
    setFullName("");
    setEmail("");
    setPassword("");
    setCreateError("");
    setShowCreateForm(true);
  };

  const createStaff = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setCreateError("");

    try {
      const created = await api.post<StaffMember>(ENDPOINTS.createUser, {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role: createRole,
      });

      setFullName("");
      setEmail("");
      setPassword("");
      setShowCreateForm(false);

      if (createRole === "KITCHEN_MANAGER") {
        // Kitchen Managers hold every kitchen permission by role; there is
        // nothing to assign here. They appear on User Accounts.
        toast.success(`${created.full_name || "Kitchen Manager"} created as Kitchen Manager. They can sign in now.`);
        return;
      }

      const updatedStaff = await api.get<StaffMember[]>(ENDPOINTS.staff);
      setStaff(updatedStaff);

      toast.success(
        `${created.full_name || "Staff account"} created. Assign the permissions they need.`
      );

      await selectStaff(created);
    } catch (err) {
      setCreateError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const savePermissions = async () => {
    if (selectedStaffId === null) return;

    setSaving(true);
    setError("");

    const assignableIds = new Set(
      assignableModules.flatMap((module) =>
        module.permissions.map((permission) => permission.id)
      )
    );

    try {
      await api.put(
        `${ENDPOINTS.staff}/${selectedStaffId}/permissions`,
        {
          permission_ids: selectedPermissionIds.filter((id) =>
            assignableIds.has(id)
          ),
        }
      );

      const detail = await api.get<StaffDetail>(
        `${ENDPOINTS.staff}/${selectedStaffId}`
      );

      applyStaffDetail(detail);

      toast.success("Staff permissions saved.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const selectAllPermissions = () => {
    setSelectedPermissionIds(
      assignableModules.flatMap((module) =>
        module.permissions.map((permission) => permission.id)
      )
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Administration"
        icon={Users}
        title="Staff Management"
        description="Create staff accounts and choose which modules each person can use."
        actions={
          <>
            <Button
              onClick={() => openCreateForm("STAFF")}
              icon={<UserPlus size={16} aria-hidden />}
            >
              Add staff
            </Button>
            <Button
              variant="secondary"
              onClick={() => openCreateForm("KITCHEN_MANAGER")}
              icon={<ChefHat size={16} aria-hidden />}
              data-add-manager
            >
              Add Kitchen Manager
            </Button>
          </>
        }
      />

      {error && (
        <Alert tone="error" onDismiss={() => setError("")}>
          {error}
        </Alert>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(280px,340px)_minmax(0,1fr)]">
        {/* Staff list */}
        <Card className="overflow-hidden lg:sticky lg:top-20">
          <CardHeader
            title="Staff members"
            subtitle={loading ? "Loading…" : `${staff.length} active accounts`}
            icon={Users}
            iconTone="brand"
            action={
              <IconButton
                size="sm"
                icon={
                  <RefreshCw
                    size={15}
                    className={refreshing ? "animate-spin" : undefined}
                  />
                }
                label="Refresh staff list"
                disabled={loading || refreshing}
                onClick={() => void loadData()}
              />
            }
          />

          {staff.length > 4 && (
            <div className="border-b border-slate-100 px-4 py-3">
              <SearchInput
                value={query}
                onChange={setQuery}
                label="Search staff"
                placeholder="Search by name or email…"
              />
            </div>
          )}

          {loading ? (
            <div className="space-y-1 p-3" role="status" aria-label="Loading">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} className="flex items-center gap-3 p-2">
                  <Skeleton className="h-9 w-9 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-3.5 w-32" />
                    <Skeleton className="h-3 w-44" />
                  </div>
                </div>
              ))}
            </div>
          ) : staff.length === 0 ? (
            <EmptyState
              compact
              icon={Users}
              title="No staff accounts yet"
              description="Add the first staff account to start assigning access."
              action={
                <Button
                  size="sm"
                  onClick={() => openCreateForm("STAFF")}
                  icon={<UserPlus size={14} aria-hidden />}
                >
                  Add staff
                </Button>
              }
            />
          ) : visibleStaff.length === 0 ? (
            <EmptyState
              compact
              title="No matching staff"
              description={`Nobody matches “${query.trim()}”.`}
            />
          ) : (
            <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto p-2 lg:max-h-[calc(100vh-14rem)]">
              {visibleStaff.map((member) => {
                const selected = selectedStaffId === member.id;

                return (
                  <li key={member.id}>
                    <button
                      type="button"
                      onClick={() => requestSelect(member)}
                      aria-pressed={selected}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition-colors",
                        selected
                          ? "bg-brand-50 ring-1 ring-brand-200"
                          : "hover:bg-slate-50"
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                          selected
                            ? "bg-brand-600 text-white"
                            : "bg-slate-100 text-slate-600"
                        )}
                      >
                        {initials(member.full_name)}
                      </span>

                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-slate-900">
                          {member.full_name}
                        </span>
                        <span className="block truncate text-xs text-slate-500">
                          {member.email}
                        </span>
                      </span>

                      <Badge tone={member.is_active ? "success" : "neutral"} dot>
                        {member.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {/* Permission matrix */}
        <Card className="overflow-hidden">
          <CardHeader
            title={
              selectedStaff ? `Access for ${selectedStaff.full_name}` : "Module access"
            }
            subtitle={
              selectedStaff
                ? selectedStaff.email
                : "Choose a staff member to manage their access"
            }
            icon={ShieldCheck}
            iconTone="brand"
            action={
              selectedStaff && !detailLoading ? (
                <div className="flex items-center gap-2">
                  {dirty && (
                    <Badge tone="warning" dot>
                      Unsaved changes
                    </Badge>
                  )}
                  <Badge tone="neutral">
                    {selectedPermissionIds.length} of {assignableCount} selected
                  </Badge>
                </div>
              ) : undefined
            }
          />

          {!selectedStaff ? (
            <EmptyState
              icon={MousePointerClick}
              title="No staff member selected"
              description="Select someone from the staff list to view and change the modules they can use."
            />
          ) : detailLoading ? (
            <Spinner label="Loading permissions…" className="py-16" />
          ) : (
            <>
              <div className="space-y-5 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-slate-500">
                    Only permissions that may be assigned to staff are listed.
                  </p>

                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={selectAllPermissions}>
                      Select all
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedPermissionIds([])}
                    >
                      Clear all
                    </Button>
                  </div>
                </div>

                {keptPermissions.length > 0 && (
                  <Alert tone="warning" title="Older permissions kept until cleanup">
                    <p>
                      These can no longer be assigned to staff. Saving leaves
                      them unchanged.
                    </p>
                    {keptPermissions.some((permission) => permission.effective === false) && (
                      <p className="mt-1">
                        Those marked “no effect” are purchase-order permissions: purchase
                        orders are handled by Admins and Kitchen Managers only, so they give
                        this person no access. They are kept as a record.
                      </p>
                    )}
                    <ul className="mt-2 flex flex-wrap gap-1.5">
                      {keptPermissions.map((permission) => (
                        <li key={permission.id}>
                          <Badge tone={permission.effective === false ? "neutral" : "warning"}>
                            <History size={11} aria-hidden />
                            {permission.module_name} · {permission.action}
                            {permission.effective === false && " · no effect"}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </Alert>
                )}

                <div className="overflow-hidden rounded-lg border border-slate-200">
                  <Table>
                    <THead>
                      <tr>
                        <TH>Module</TH>
                        {matrixActions.map((action) => (
                          <TH key={action} align="center" className="w-24">
                            {ACTION_LABELS[action] ?? action}
                          </TH>
                        ))}
                        <TH align="center" className="w-20">
                          All
                        </TH>
                      </tr>
                    </THead>
                    <TBody>
                      {assignableModules.map((module) => {
                        const ids = module.permissions.map((p) => p.id);
                        const onCount = ids.filter((id) =>
                          selectedPermissionIds.includes(id)
                        ).length;

                        return (
                          <TR key={module.id}>
                            <TD className="font-medium text-slate-900">
                              {module.name}
                            </TD>

                            {matrixActions.map((action) => {
                              const permission = module.permissions.find(
                                (p) => p.action === action
                              );

                              return (
                                <TD key={action} align="center">
                                  {permission ? (
                                    <input
                                      type="checkbox"
                                      checked={selectedPermissionIds.includes(
                                        permission.id
                                      )}
                                      onChange={() =>
                                        togglePermission(permission.id)
                                      }
                                      aria-label={`${ACTION_LABELS[action] ?? action} ${module.name}`}
                                      className="h-4 w-4 cursor-pointer rounded border-slate-300 accent-brand-600"
                                    />
                                  ) : (
                                    <span
                                      className="text-slate-300"
                                      aria-label="Not available"
                                    >
                                      —
                                    </span>
                                  )}
                                </TD>
                              );
                            })}

                            <TD align="center">
                              <input
                                type="checkbox"
                                checked={onCount === ids.length}
                                ref={(element) => {
                                  if (element) {
                                    element.indeterminate =
                                      onCount > 0 && onCount < ids.length;
                                  }
                                }}
                                onChange={() => toggleModule(module)}
                                aria-label={`All ${module.name} permissions`}
                                className="h-4 w-4 cursor-pointer rounded border-slate-300 accent-brand-600"
                              />
                            </TD>
                          </TR>
                        );
                      })}
                    </TBody>
                  </Table>
                </div>
              </div>

              <div className="flex flex-col-reverse gap-2 border-t border-slate-100 bg-slate-50/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-end">
                <Button
                  variant="secondary"
                  onClick={() => setSelectedPermissionIds(savedPermissionIds)}
                  disabled={!dirty || saving}
                  icon={<RotateCcw size={15} aria-hidden />}
                >
                  Discard changes
                </Button>
                <Button
                  onClick={() => void savePermissions()}
                  loading={saving}
                  disabled={!dirty}
                  icon={<Save size={15} aria-hidden />}
                >
                  Save permissions
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>

      <Modal
        open={showCreateForm}
        onClose={() => {
          if (!creating) setShowCreateForm(false);
        }}
        dismissible={!creating}
        title={createRole === "KITCHEN_MANAGER" ? "Add Kitchen Manager account" : "Add staff account"}
        description={createRole === "KITCHEN_MANAGER"
          ? "Kitchen Managers run every kitchen operation on this campus but cannot manage users or permissions."
          : "New accounts get the Staff role and no module access until you assign it."}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setShowCreateForm(false)}
              disabled={creating}
            >
              Cancel
            </Button>
            <Button type="submit" form="create-staff-form" loading={creating}>
              Create account
            </Button>
          </>
        }
      >
        <form
          id="create-staff-form"
          onSubmit={createStaff}
          className="space-y-5"
        >
          {createError && <Alert tone="error">{createError}</Alert>}

          <Input
            label="Full name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="e.g. Priya Nair"
            autoComplete="off"
            minLength={2}
            maxLength={150}
            required
            data-autofocus
          />

          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
            autoComplete="off"
            required
          />

          <Input
            label="Temporary password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            hint="At least 8 characters. Share it with the person securely."
            autoComplete="new-password"
            minLength={8}
            required
          />
        </form>
      </Modal>

      <ConfirmDialog
        open={pendingSwitch !== null}
        tone="warning"
        title="Discard unsaved changes?"
        description={
          <>
            You changed {selectedStaff?.full_name ?? "this person"}&apos;s
            access without saving. Switching to{" "}
            <strong className="font-semibold text-slate-800">
              {pendingSwitch?.full_name}
            </strong>{" "}
            will discard those changes.
          </>
        }
        confirmLabel="Discard and switch"
        onConfirm={() => {
          const member = pendingSwitch;
          setPendingSwitch(null);
          if (member) void selectStaff(member);
        }}
        onCancel={() => setPendingSwitch(null)}
      />
    </div>
  );
}
