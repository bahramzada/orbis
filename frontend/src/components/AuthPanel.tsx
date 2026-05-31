import { Loader2, LockKeyhole } from "lucide-react";
import type { FormEvent } from "react";

import type { SystemSettings } from "../types";

type AuthMode = "login" | "register";
type AuthAction = "idle" | "login" | "register" | "logout";

export function AuthPanel({
  authMode,
  authAction,
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
  authAction: AuthAction;
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
  const isBusy = authAction === "login" || authAction === "register";
  const submitDisabled =
    isBusy ||
    email.trim().length < 3 ||
    password.length < 8 ||
    (authMode === "register" && registerDisabled);
  const submitLabel = getSubmitLabel(authMode, authAction);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitDisabled) {
      return;
    }
    if (authMode === "login") {
      onLogin();
      return;
    }
    onRegister();
  }

  return (
    <form className="auth-panel" aria-busy={isBusy} onSubmit={handleSubmit}>
      <div className="auth-lock">
        <LockKeyhole size={18} />
      </div>
      <div className="auth-tabs">
        <button
          className={authMode === "login" ? "active" : ""}
          disabled={isBusy}
          onClick={() => onAuthModeChange("login")}
          type="button"
        >
          Login
        </button>
        <button
          className={authMode === "register" ? "active" : ""}
          disabled={registerDisabled || isBusy}
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
            disabled={isBusy}
            onChange={(event) => onDisplayNameChange(event.currentTarget.value)}
            value={displayName}
          />
        </label>
      ) : null}
      <label>
        <span>Email</span>
        <input
          autoComplete="email"
          disabled={isBusy}
          onChange={(event) => onEmailChange(event.currentTarget.value)}
          type="email"
          value={email}
        />
      </label>
      <label>
        <span>Password</span>
        <input
          autoComplete={authMode === "login" ? "current-password" : "new-password"}
          disabled={isBusy}
          onChange={(event) => onPasswordChange(event.currentTarget.value)}
          type="password"
          value={password}
        />
      </label>
      {authError ? <div className="auth-error">{authError}</div> : null}
      {isBusy ? (
        <div className="auth-status" aria-live="polite">
          <Loader2 className="spin" size={15} />
          {authMode === "login" ? "Checking your session..." : "Creating account..."}
        </div>
      ) : null}
      {authMode === "register" && registerDisabled ? null : (
          <button
            className={`auth-submit ${isBusy ? "loading" : ""}`}
            disabled={submitDisabled}
            type="submit"
          >
            {isBusy ? <Loader2 className="spin" size={16} /> : null}
            {submitLabel}
          </button>
      )}
    </form>
  );
}

function getSubmitLabel(authMode: AuthMode, authAction: AuthAction): string {
  if (authAction === "login") {
    return "Logging in";
  }
  if (authAction === "register") {
    return "Creating account";
  }
  return authMode === "login" ? "Login" : "Create guest account";
}
