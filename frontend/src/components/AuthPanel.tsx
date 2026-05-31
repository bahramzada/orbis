import { LogOut, ShieldCheck, UserRound } from "lucide-react";

import type { AdminUser, AuthUser, SystemSettings, UserRole } from "../types";

type AuthMode = "login" | "register";

export function AuthPanel({
  authMode,
  authError,
  authUser,
  email,
  password,
  displayName,
  systemSettings,
  adminUsers,
  onAuthModeChange,
  onEmailChange,
  onPasswordChange,
  onDisplayNameChange,
  onLogin,
  onRegister,
  onLogout,
  onRefreshAdmin,
  onSystemSettingChange,
  onUserRoleChange,
  onUserActiveChange
}: {
  authMode: AuthMode;
  authError: string;
  authUser: AuthUser | null;
  email: string;
  password: string;
  displayName: string;
  systemSettings: SystemSettings | null;
  adminUsers: AdminUser[];
  onAuthModeChange: (mode: AuthMode) => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onLogin: () => void;
  onRegister: () => void;
  onLogout: () => void;
  onRefreshAdmin: () => void;
  onSystemSettingChange: (field: keyof SystemSettings, value: boolean) => void;
  onUserRoleChange: (userId: string, role: UserRole) => void;
  onUserActiveChange: (userId: string, isActive: boolean) => void;
}) {
  return (
    <section className="auth-panel">
      {authUser ? (
        <>
          <div className="auth-user-row">
            <span className="auth-avatar">
              <UserRound size={16} />
            </span>
            <div>
              <strong>{authUser.display_name || authUser.email}</strong>
              <small>
                {authUser.email} · {authUser.role}
              </small>
            </div>
            <button className="icon-text-button" onClick={onLogout} type="button">
              <LogOut size={15} />
              Logout
            </button>
          </div>
          {authUser.role === "admin" ? (
            <AdminControls
              adminUsers={adminUsers}
              systemSettings={systemSettings}
              onRefreshAdmin={onRefreshAdmin}
              onSystemSettingChange={onSystemSettingChange}
              onUserActiveChange={onUserActiveChange}
              onUserRoleChange={onUserRoleChange}
            />
          ) : null}
        </>
      ) : (
        <>
          <div className="auth-tabs">
            <button
              className={authMode === "login" ? "active" : ""}
              onClick={() => onAuthModeChange("login")}
              type="button"
            >
              Login
            </button>
            <button
              className={authMode === "register" ? "active" : ""}
              onClick={() => onAuthModeChange("register")}
              type="button"
            >
              Register
            </button>
          </div>
          {authMode === "register" ? (
            <label>
              <span>Name</span>
              <input
                autoComplete="name"
                onChange={(event) => onDisplayNameChange(event.currentTarget.value)}
                value={displayName}
              />
            </label>
          ) : null}
          <label>
            <span>Email</span>
            <input
              autoComplete="email"
              onChange={(event) => onEmailChange(event.currentTarget.value)}
              type="email"
              value={email}
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete={authMode === "login" ? "current-password" : "new-password"}
              onChange={(event) => onPasswordChange(event.currentTarget.value)}
              type="password"
              value={password}
            />
          </label>
          {authError ? <div className="auth-error">{authError}</div> : null}
          <button
            className="auth-submit"
            disabled={email.trim().length < 3 || password.length < 8}
            onClick={authMode === "login" ? onLogin : onRegister}
            type="button"
          >
            {authMode === "login" ? "Login" : "Create guest account"}
          </button>
        </>
      )}
    </section>
  );
}

function AdminControls({
  adminUsers,
  systemSettings,
  onRefreshAdmin,
  onSystemSettingChange,
  onUserRoleChange,
  onUserActiveChange
}: {
  adminUsers: AdminUser[];
  systemSettings: SystemSettings | null;
  onRefreshAdmin: () => void;
  onSystemSettingChange: (field: keyof SystemSettings, value: boolean) => void;
  onUserRoleChange: (userId: string, role: UserRole) => void;
  onUserActiveChange: (userId: string, isActive: boolean) => void;
}) {
  return (
    <details className="admin-panel">
      <summary>
        <span>
          <ShieldCheck size={16} />
          Admin Panel
        </span>
        <small>{adminUsers.length} users</small>
      </summary>
      <div className="admin-switches">
        <label>
          <input
            checked={systemSettings?.system_enabled ?? true}
            onChange={(event) =>
              onSystemSettingChange("system_enabled", event.currentTarget.checked)
            }
            type="checkbox"
          />
          System enabled
        </label>
        <label>
          <input
            checked={systemSettings?.register_enabled ?? true}
            onChange={(event) =>
              onSystemSettingChange("register_enabled", event.currentTarget.checked)
            }
            type="checkbox"
          />
          Registration enabled
        </label>
      </div>
      <button className="secondary-button" onClick={onRefreshAdmin} type="button">
        Refresh users
      </button>
      <div className="admin-user-list">
        {adminUsers.map((user) => (
          <article key={user.id}>
            <div>
              <strong>{user.display_name || user.email}</strong>
              <small>{user.email}</small>
            </div>
            <select
              onChange={(event) => onUserRoleChange(user.id, event.currentTarget.value as UserRole)}
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
              Active
            </label>
          </article>
        ))}
      </div>
    </details>
  );
}
