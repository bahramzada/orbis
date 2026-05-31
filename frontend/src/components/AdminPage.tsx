import { RefreshCw, ShieldCheck, SlidersHorizontal, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";

import type { AdminUser, AuthUser, SystemSettings, UserRole } from "../types";

type RoleFilter = UserRole | "all";

export function AdminPage({
  adminUsers,
  authUser,
  error,
  systemSettings,
  onRefreshAdmin,
  onSystemSettingChange,
  onUserActiveChange,
  onUserRoleChange
}: {
  adminUsers: AdminUser[];
  authUser: AuthUser;
  error: string;
  systemSettings: SystemSettings | null;
  onRefreshAdmin: () => void;
  onSystemSettingChange: (field: keyof SystemSettings, value: boolean) => void;
  onUserActiveChange: (userId: string, isActive: boolean) => void;
  onUserRoleChange: (userId: string, role: UserRole) => void;
}) {
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");

  const stats = useMemo(() => {
    const activeUsers = adminUsers.filter((user) => user.is_active);
    return {
      total: adminUsers.length,
      active: activeUsers.length,
      disabled: adminUsers.length - activeUsers.length,
      admins: adminUsers.filter((user) => user.role === "admin").length,
      vip: adminUsers.filter((user) => user.role === "vip").length,
      guests: adminUsers.filter((user) => user.role === "guest").length
    };
  }, [adminUsers]);

  const filteredUsers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return adminUsers.filter((user) => {
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      const matchesQuery =
        !normalizedQuery ||
        user.email.toLowerCase().includes(normalizedQuery) ||
        user.display_name.toLowerCase().includes(normalizedQuery);
      return matchesRole && matchesQuery;
    });
  }, [adminUsers, query, roleFilter]);

  if (authUser.role !== "admin") {
    return (
      <section className="admin-page">
        <article className="admin-card access-denied">
          <ShieldCheck size={28} />
          <div>
            <h2>Admin access required</h2>
            <p>This page is available only for admin users.</p>
          </div>
        </article>
      </section>
    );
  }

  return (
    <section className="admin-page">
      <div className="admin-hero">
        <div>
          <p className="eyebrow">Admin</p>
          <h2>System Console</h2>
        </div>
        <button className="secondary-button" onClick={onRefreshAdmin} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {error ? <div className="error-box">{error}</div> : null}

      <div className="admin-stat-grid">
        <StatCard label="Users" value={stats.total} detail={`${stats.active} active`} />
        <StatCard label="Admins" value={stats.admins} detail="full access" />
        <StatCard label="VIP" value={stats.vip} detail="priority users" />
        <StatCard label="Guests" value={stats.guests} detail={`${stats.disabled} disabled`} />
      </div>

      <div className="admin-control-grid">
        <article className="admin-card">
          <div className="admin-card-heading">
            <SlidersHorizontal size={18} />
            <h3>System Controls</h3>
          </div>
          <div className="admin-switches detailed">
            <label>
              <span>
                <strong>System</strong>
                <small>{systemSettings?.system_enabled === false ? "Closed" : "Open"}</small>
              </span>
              <input
                checked={systemSettings?.system_enabled ?? true}
                onChange={(event) =>
                  onSystemSettingChange("system_enabled", event.currentTarget.checked)
                }
                type="checkbox"
              />
            </label>
            <label>
              <span>
                <strong>Registration</strong>
                <small>
                  {systemSettings?.register_enabled === false ? "Closed" : "Open"}
                </small>
              </span>
              <input
                checked={systemSettings?.register_enabled ?? true}
                onChange={(event) =>
                  onSystemSettingChange("register_enabled", event.currentTarget.checked)
                }
                type="checkbox"
              />
            </label>
          </div>
        </article>

        <article className="admin-card">
          <div className="admin-card-heading">
            <UsersRound size={18} />
            <h3>Role Distribution</h3>
          </div>
          <div className="role-meter">
            <span>
              <strong>{stats.admins}</strong>
              Admin
            </span>
            <span>
              <strong>{stats.vip}</strong>
              VIP
            </span>
            <span>
              <strong>{stats.guests}</strong>
              Guest
            </span>
          </div>
        </article>
      </div>

      <article className="admin-card admin-users-card">
        <div className="admin-users-header">
          <div>
            <h3>User Management</h3>
            <p>{filteredUsers.length} visible accounts</p>
          </div>
          <div className="admin-filters">
            <input
              aria-label="Search users"
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="Search users"
              value={query}
            />
            <select
              aria-label="Filter by role"
              onChange={(event) => setRoleFilter(event.currentTarget.value as RoleFilter)}
              value={roleFilter}
            >
              <option value="all">All roles</option>
              <option value="admin">Admin</option>
              <option value="vip">VIP</option>
              <option value="guest">Guest</option>
            </select>
          </div>
        </div>

        <div className="admin-user-table">
          <div className="admin-user-table-head">
            <span>User</span>
            <span>Role</span>
            <span>Status</span>
            <span>Created</span>
            <span>Updated</span>
          </div>
          {filteredUsers.map((user) => (
            <article key={user.id} className={!user.is_active ? "disabled-user" : ""}>
              <div>
                <strong>{user.display_name || user.email}</strong>
                <small>{user.email}</small>
              </div>
              <select
                onChange={(event) =>
                  onUserRoleChange(user.id, event.currentTarget.value as UserRole)
                }
                value={user.role}
              >
                <option value="guest">guest</option>
                <option value="vip">vip</option>
                <option value="admin">admin</option>
              </select>
              <label className="active-toggle">
                <input
                  checked={user.is_active}
                  onChange={(event) => onUserActiveChange(user.id, event.currentTarget.checked)}
                  type="checkbox"
                />
                {user.is_active ? "Active" : "Disabled"}
              </label>
              <time>{formatDate(user.created_at)}</time>
              <time>{formatDate(user.updated_at)}</time>
            </article>
          ))}
        </div>
      </article>
    </section>
  );
}

function StatCard({
  detail,
  label,
  value
}: {
  detail: string;
  label: string;
  value: number;
}) {
  return (
    <article className="admin-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric"
  });
}
