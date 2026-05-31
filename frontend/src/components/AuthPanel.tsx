import { LockKeyhole } from "lucide-react";

import type { SystemSettings } from "../types";

type AuthMode = "login" | "register";

export function AuthPanel({
  authMode,
  authError,
  email,
  password,
  displayName,
  systemSettings,
  onAuthModeChange,
  onEmailChange,
  onPasswordChange,
  onDisplayNameChange,
  onLogin,
  onRegister
}: {
  authMode: AuthMode;
  authError: string;
  email: string;
  password: string;
  displayName: string;
  systemSettings: SystemSettings | null;
  onAuthModeChange: (mode: AuthMode) => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onLogin: () => void;
  onRegister: () => void;
}) {
  const registerDisabled = systemSettings?.register_enabled === false;

  return (
    <section className="auth-panel">
      <div className="auth-lock">
        <LockKeyhole size={18} />
      </div>
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
          disabled={registerDisabled}
          onClick={() => onAuthModeChange("register")}
          type="button"
        >
          Register
        </button>
      </div>
      {registerDisabled && authMode === "register" ? (
        <div className="auth-error">Registration is disabled.</div>
      ) : null}
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
      {authMode === "register" && registerDisabled ? null : (
          <button
            className="auth-submit"
            disabled={email.trim().length < 3 || password.length < 8}
            onClick={authMode === "login" ? onLogin : onRegister}
            type="button"
          >
            {authMode === "login" ? "Login" : "Create guest account"}
          </button>
      )}
    </section>
  );
}
