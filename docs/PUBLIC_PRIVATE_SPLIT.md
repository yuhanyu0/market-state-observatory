# Public / private split

## Public repository

- architecture and schemas;
- synthetic examples;
- redacted public status;
- validation methodology;
- public-safe State Certificates;
- React static product source and build configuration;
- provider interfaces without credentials.

## Private or local evidence vault

- API credentials;
- raw provider payloads subject to licensing restrictions;
- broker account information;
- private positions and orders;
- proprietary event feeds;
- unreleased research data.

The public publisher must fail closed when it detects secret-like keys or paths.
Generated public JSON may enter the repository only below `public/data/` or the
`data/` root of the isolated `public-data` branch. Real runtime data is outside
Git under the current user's LocalAppData directory.
