# Publication Firewall

The public site never reads the private runtime. Publication is a one-way,
fail-closed pipeline:

1. a private quality artifact is selected explicitly;
2. `public_projection.py` derives aggregate state;
3. `redactor.py` rejects raw and near-raw provider containers;
4. the JSON policy and schema validators run;
5. forbidden fields, credentials, local paths, positions, and orders are scanned;
6. an immutable publication manifest is generated;
7. only `data/` in the `public-data` worktree changes;
8. GitHub Pages overlays those JSON files on the product build.

Raw SIP quotes, trades, bars, response payloads, request identifiers, account
information, execution details, private Data Shadow files, and Windows paths
are never public artifacts. This remains true even when automated publication
is enabled.
