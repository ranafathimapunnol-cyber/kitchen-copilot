"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Plus, Users, ShieldCheck, Save, RefreshCw } from "lucide-react";

import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
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
};

type StaffDetail = {
  staff: StaffMember;
  permissions: AssignedPermission[];
};

function getErrorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

export default function StaffManagementPage() {
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [modules, setModules] = useState<PermissionModule[]>([]);
  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [selectedPermissionIds, setSelectedPermissionIds] = useState<number[]>([]);
  // Older permissions that can no longer be assigned to staff. They are
  // shown for information and kept unchanged when saving.
  const [keptPermissions, setKeptPermissions] = useState<AssignedPermission[]>([]);

  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

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

  const applyStaffDetail = (detail: StaffDetail) => {
    setSelectedPermissionIds(
      detail.permissions
        .filter((permission) => permission.assignable)
        .map((permission) => permission.id)
    );
    setKeptPermissions(
      detail.permissions.filter((permission) => !permission.assignable)
    );
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [staffResult, modulesResult] = await Promise.all([
        api.get<StaffMember[]>(ENDPOINTS.staff),
        api.get<PermissionModule[]>(ENDPOINTS.authorizationModules),
      ]);

      setStaff(staffResult);
      setModules(modulesResult);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [loadData]);

  const selectStaff = async (member: StaffMember) => {
    setSelectedStaffId(member.id);
    setDetailLoading(true);
    setError("");
    setSuccess("");

    try {
      const detail = await api.get<StaffDetail>(
        `${ENDPOINTS.staff}/${member.id}`
      );

      applyStaffDetail(detail);
    } catch (err) {
      setSelectedPermissionIds([]);
      setKeptPermissions([]);
      setError(getErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const togglePermission = (permissionId: number) => {
    setSelectedPermissionIds((current) =>
      current.includes(permissionId)
        ? current.filter((id) => id !== permissionId)
        : [...current, permissionId]
    );
  };

  const createStaff = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setError("");
    setSuccess("");

    try {
      const created = await api.post<StaffMember>(ENDPOINTS.createUser, {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role: "STAFF",
      });

      setFullName("");
      setEmail("");
      setPassword("");
      setShowCreateForm(false);

      const updatedStaff = await api.get<StaffMember[]>(ENDPOINTS.staff);
      setStaff(updatedStaff);

      setSuccess(
        "Staff account created. Assign the required permissions below."
      );

      await selectStaff(created);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const savePermissions = async () => {
    if (selectedStaffId === null) return;

    setSaving(true);
    setError("");
    setSuccess("");

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

      setSuccess("Staff permissions saved successfully.");
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
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Staff Management
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Create staff accounts and manage their module access.
          </p>
        </div>

        <Button
          onClick={() => {
            setShowCreateForm((value) => !value);
            setError("");
            setSuccess("");
          }}
        >
          <Plus size={17} className="mr-2" />
          Add Staff
        </Button>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {success && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {success}
        </div>
      )}

      {showCreateForm && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">
            Create Staff Account
          </h2>

          <form onSubmit={createStaff} className="grid gap-4 md:grid-cols-2">
            <Input
              label="Full name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Enter staff name"
              minLength={2}
              maxLength={150}
              required
            />

            <Input
              label="Email address"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="staff@example.com"
              required
            />

            <Input
              label="Temporary password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Minimum 8 characters"
              minLength={8}
              required
            />

            <div className="flex items-end gap-2">
              <Button type="submit" disabled={creating}>
                {creating ? "Creating..." : "Create Staff"}
              </Button>

              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowCreateForm(false)}
              >
                Cancel
              </Button>
            </div>
          </form>

          <p className="mt-3 text-xs text-slate-500">
            New accounts receive the STAFF role and no permissions until you
            assign them.
          </p>
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.7fr)]">
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div className="flex items-center gap-2">
              <Users size={18} className="text-blue-700" />
              <h2 className="font-semibold text-slate-900">Staff Members</h2>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {staff.length}
              </span>
            </div>

            <button
              type="button"
              onClick={() => void loadData()}
              aria-label="Refresh staff list"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
            >
              <RefreshCw size={16} />
            </button>
          </div>

          {loading ? (
            <p className="p-5 text-sm text-slate-500">Loading staff...</p>
          ) : staff.length === 0 ? (
            <div className="p-6 text-center">
              <Users className="mx-auto mb-2 text-slate-300" size={28} />
              <p className="text-sm font-medium text-slate-700">
                No staff accounts yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Select Add Staff to create the first account.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {staff.map((member) => (
                <button
                  type="button"
                  key={member.id}
                  onClick={() => void selectStaff(member)}
                  className={`w-full px-5 py-4 text-left transition hover:bg-slate-50 ${
                    selectedStaffId === member.id ? "bg-blue-50" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-slate-900">
                      {member.full_name}
                    </span>

                    <span
                      className={`rounded-full px-2 py-1 text-[11px] font-medium ${
                        member.is_active
                          ? "bg-green-50 text-green-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {member.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>

                  <p className="mt-1 truncate text-xs text-slate-500">
                    {member.email}
                  </p>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-4">
            <ShieldCheck size={18} className="text-blue-700" />
            <div>
              <h2 className="font-semibold text-slate-900">
                Module Permissions
              </h2>
              <p className="text-xs text-slate-500">
                {selectedStaff
                  ? `Manage access for ${selectedStaff.full_name}`
                  : "Choose a staff member to manage access"}
              </p>
            </div>
          </div>

          {!selectedStaff ? (
            <div className="p-10 text-center text-sm text-slate-500">
              Select a staff member from the list to manage permissions.
            </div>
          ) : detailLoading ? (
            <p className="p-6 text-sm text-slate-500">
              Loading permissions...
            </p>
          ) : (
            <>
              <div className="space-y-4 p-5">
                <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>
                    Selected permissions:{" "}
                    <strong className="text-slate-800">
                      {selectedPermissionIds.length}
                    </strong>
                  </span>

                  <button
                    type="button"
                    onClick={selectAllPermissions}
                    className="font-semibold text-blue-700 hover:underline"
                  >
                    Select all
                  </button>

                  <button
                    type="button"
                    onClick={() => setSelectedPermissionIds([])}
                    className="font-semibold text-blue-700 hover:underline"
                  >
                    Clear all
                  </button>
                </div>

                <p className="text-xs text-slate-500">
                  Only permissions that may be assigned to staff are listed.
                </p>

                {keptPermissions.length > 0 && (
                  <div
                    role="note"
                    className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
                  >
                    <p className="font-semibold">
                      Older permissions kept until cleanup
                    </p>
                    <p className="mt-1 text-xs">
                      These permissions can no longer be assigned to staff.
                      Saving leaves them unchanged.
                    </p>
                    <ul className="mt-2 flex flex-wrap gap-2 text-xs">
                      {keptPermissions.map((permission) => (
                        <li
                          key={permission.id}
                          className="rounded-full bg-white px-2 py-1 font-medium"
                        >
                          {permission.module_name} · {permission.action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {assignableModules.map((module) => (
                  <div
                    key={module.id}
                    className="overflow-hidden rounded-lg border border-slate-200"
                  >
                    <div className="border-b border-slate-100 bg-slate-50 px-4 py-3">
                      <h3 className="text-sm font-semibold text-slate-800">
                        {module.name}
                      </h3>
                    </div>

                    <div className="grid gap-3 p-4 sm:grid-cols-3">
                      {module.permissions.map((permission) => (
                        <label
                          key={permission.id}
                          className="flex cursor-pointer items-center gap-2 text-sm text-slate-700"
                        >
                          <input
                            type="checkbox"
                            checked={selectedPermissionIds.includes(
                              permission.id
                            )}
                            onChange={() => togglePermission(permission.id)}
                            className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-600"
                          />
                          {permission.action}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-end border-t border-slate-100 px-5 py-4">
                <Button onClick={savePermissions} disabled={saving}>
                  <Save size={16} className="mr-2" />
                  {saving ? "Saving..." : "Save Permissions"}
                </Button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
