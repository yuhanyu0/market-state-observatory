# ADR 0010: Current-User DPAPI Credentials

## Status

Accepted for the Windows collector host.

## Decision

Alpaca credentials are entered interactively into a `PSCredential`, exported
with `Export-Clixml`, and protected by current-user DPAPI plus a current-user
ACL. The runtime imports them only to populate one collector child process.

Plain `.env`, `setx`, unauthenticated SecretStore, repository secrets, command
arguments, logs, and manifests are not credential stores. Provider errors expose
only error type and collector request ID.
