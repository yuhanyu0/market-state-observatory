# Release Notes 0.4.5

## Windows Runtime Lifecycle Control

This compatibility patch gives the scheduler-owned runtime tree one operating-
system lifecycle. The frozen launcher creates the actual base Python interpreter
suspended, assigns it to a named Windows Job Object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, freezes process ownership, and resumes it.
Launcher exit, crash, or Task Scheduler termination therefore closes the Job and
terminates its descendants.

`ops/windows/stop_runtime.ps1` is identity scoped. It verifies task, release,
executable, PID creation time, and Job ownership; it never stops Python by name.
Release selection and startup now reject live MSO owners and inconsistent locks.
The operator console reports process truth independently from task state.

The 2026-08-17 v0.4.3 interruption remains immutable incomplete evidence. No
backfill or PASS was produced. v0.4.5 starts a new experiment lane and requires
three new scheduler-driven PASS dates before Formal Data Shadow can be reviewed.

Formal Data Shadow and Model Shadow remain stopped. Paper positions and real
orders remain zero. The v0.4.5 scheduler is not installed by this release build.
