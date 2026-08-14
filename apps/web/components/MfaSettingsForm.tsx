"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";

type Setup = {
  secret: string;
  otpauth_uri: string;
};

type SecurityResponse = {
  message?: string;
  secret?: string;
  otpauth_uri?: string;
  recovery_codes?: string[];
  detail?: string;
};

export function MfaSettingsForm({
  enabled,
}: {
  enabled: boolean;
}) {
  const router = useRouter();

  const [setup, setSetup] =
    useState<Setup | null>(null);

  const [qrDataUrl, setQrDataUrl] =
    useState("");

  const [recoveryCodes, setRecoveryCodes] =
    useState<string[]>([]);

  const [code, setCode] = useState("");
  const [password, setPassword] =
    useState("");

  const [message, setMessage] =
    useState("");

  const [busy, setBusy] =
    useState(false);

  useEffect(() => {
    let cancelled = false;

    async function buildQr() {
      if (!setup?.otpauth_uri) {
        setQrDataUrl("");
        return;
      }

      try {
        const url = await QRCode.toDataURL(
          setup.otpauth_uri,
          {
            width: 240,
            margin: 2,
            errorCorrectionLevel: "M",
          },
        );

        if (!cancelled) {
          setQrDataUrl(url);
        }
      } catch {
        if (!cancelled) {
          setQrDataUrl("");
        }
      }
    }

    void buildQr();

    return () => {
      cancelled = true;
    };
  }, [setup]);

  async function send(
    body: Record<string, unknown>,
  ): Promise<SecurityResponse | null> {
    setBusy(true);
    setMessage("");

    try {
      const response = await fetch(
        "/api/settings/security",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        },
      );

      const data =
        (await response
          .json()
          .catch(() => ({}))) as SecurityResponse;

      if (!response.ok) {
        setMessage(
          data.detail ||
            "Security update failed.",
        );
        return null;
      }

      return data;
    } finally {
      setBusy(false);
    }
  }

  async function beginSetup() {
    const data = await send({
      action: "setup",
    });

    if (
      data?.secret &&
      data.otpauth_uri
    ) {
      setSetup({
        secret: data.secret,
        otpauth_uri: data.otpauth_uri,
      });

      setCode("");
      setRecoveryCodes([]);
    }
  }

  async function confirm() {
    const data = await send({
      action: "confirm",
      code,
    });

    if (!data) return;

    const codes =
      data.recovery_codes || [];

    setRecoveryCodes(codes);
    setMessage(
      data.message ||
        "Authenticator enabled.",
    );

    setSetup(null);
    setCode("");
  }

  async function regenerate() {
    const data = await send({
      action: "regenerate",
      code,
      password,
    });

    if (!data) return;

    setRecoveryCodes(
      data.recovery_codes || [],
    );

    setMessage(
      data.message ||
        "Recovery codes regenerated.",
    );

    setCode("");
    setPassword("");
  }

  async function disable() {
    const data = await send({
      action: "disable",
      code,
      password,
    });

    if (!data) return;

    setMessage(
      data.message ||
        "Authenticator disabled.",
    );

    window.setTimeout(() => {
      router.push("/login");
      router.refresh();
    }, 500);
  }

  async function copyRecoveryCodes() {
    if (!recoveryCodes.length) return;

    await navigator.clipboard.writeText(
      recoveryCodes.join("\n"),
    );

    setMessage(
      "Recovery codes copied. Store them somewhere secure.",
    );
  }

  function downloadRecoveryCodes() {
    if (!recoveryCodes.length) return;

    const contents = [
      "Hidden Oasis Staff Payroll",
      "MFA Recovery Codes",
      "",
      "Each code can be used once.",
      "Store these securely.",
      "",
      ...recoveryCodes,
      "",
    ].join("\n");

    const blob = new Blob(
      [contents],
      { type: "text/plain;charset=utf-8" },
    );

    const url =
      URL.createObjectURL(blob);

    const link =
      document.createElement("a");

    link.href = url;
    link.download =
      "hidden-oasis-mfa-recovery-codes.txt";

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  }

  function finishRecoveryStep() {
    setRecoveryCodes([]);
    router.push("/login");
    router.refresh();
  }

  if (recoveryCodes.length) {
    return (
      <div className="form-panel">
        <div>
          <span className="eyebrow">
            Save now
          </span>
          <h2>Recovery codes</h2>
          <p className="muted">
            These codes are shown only now.
            Each code works once. Saving new
            codes invalidates any previous set.
          </p>
        </div>

        <div
          className="copy-box"
          aria-label="MFA recovery codes"
        >
          <pre
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              fontFamily: "monospace",
            }}
          >
            {recoveryCodes.join("\n")}
          </pre>
        </div>

        <div className="action-row">
          <button
            className="button"
            type="button"
            onClick={copyRecoveryCodes}
          >
            Copy codes
          </button>

          <button
            className="button secondary"
            type="button"
            onClick={downloadRecoveryCodes}
          >
            Download .txt
          </button>

          <button
            className="button"
            type="button"
            onClick={finishRecoveryStep}
          >
            I saved these codes
          </button>
        </div>

        {message ? (
          <p
            className="muted"
            role="status"
          >
            {message}
          </p>
        ) : null}
      </div>
    );
  }

  if (enabled) {
    return (
      <div className="form-panel">
        <div>
          <span className="eyebrow">
            Enabled
          </span>
          <h2>Authenticator protection</h2>
          <p className="muted">
            Use your current password and
            authenticator code to regenerate
            recovery codes or disable MFA.
          </p>
        </div>

        <div className="form-grid">
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) =>
                setPassword(
                  event.target.value,
                )
              }
            />
          </label>

          <label>
            Authenticator code
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) =>
                setCode(
                  event.target.value
                    .replace(/\D/g, "")
                    .slice(0, 6),
                )
              }
            />
          </label>
        </div>

        <div className="action-row">
          <button
            className="button"
            type="button"
            disabled={
              busy ||
              !password ||
              code.length !== 6
            }
            onClick={regenerate}
          >
            Generate new recovery codes
          </button>

          <button
            className="button danger"
            type="button"
            disabled={
              busy ||
              !password ||
              code.length !== 6
            }
            onClick={disable}
          >
            Disable authenticator
          </button>
        </div>

        {message ? (
          <p
            className="muted"
            role="status"
          >
            {message}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid">
      {!setup ? (
        <>
          <p className="muted">
            Add an authenticator app as a
            second factor for sign-in.
          </p>

          <button
            className="button"
            type="button"
            disabled={busy}
            onClick={beginSetup}
          >
            Set up authenticator
          </button>
        </>
      ) : null}

      {setup ? (
        <>
          <div>
            <h2>
              Scan with your authenticator
            </h2>
            <p className="muted">
              Scan the QR code, or enter the
              setup key manually.
            </p>
          </div>

          {qrDataUrl ? (
            <div
              style={{
                display: "inline-flex",
                padding: 12,
                background: "white",
                borderRadius: 12,
                width: "fit-content",
              }}
            >
              {/* Generated entirely from the
                  local otpauth URI. */}
              <img
                src={qrDataUrl}
                width={240}
                height={240}
                alt="Authenticator setup QR code"
              />
            </div>
          ) : (
            <p className="muted">
              QR generation unavailable.
              Use the setup key below.
            </p>
          )}

          <div className="copy-box">
            <strong>
              {setup.secret}
            </strong>
          </div>

          <a
            className="primary-link"
            href={setup.otpauth_uri}
          >
            Open authenticator app
          </a>

          <div className="form-grid">
            <label>
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) =>
                  setCode(
                    event.target.value
                      .replace(/\D/g, "")
                      .slice(0, 6),
                  )
                }
              />
            </label>

            <button
              className="button"
              type="button"
              disabled={
                busy ||
                code.length !== 6
              }
              onClick={confirm}
            >
              Confirm authenticator
            </button>
          </div>
        </>
      ) : null}

      {message ? (
        <p
          className="muted"
          role="status"
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
