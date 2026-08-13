# Release Notes 0.4.3

This safety patch changes the Windows scheduler default to rehearsal and uses
separate `MSO-Daily-Rehearsal` and `MSO-Daily-Formal` task identities. A formal
task cannot be installed or run without an immutable GO authorization matching
the current Git SHA, wheel, experiment lane, universe, membership, schema,
quality policy, and a verified three-session soak result.

Rehearsal artifacts are forced to remain outside the formal 20-day gate and
formal data-only artifacts remain outside Model Shadow. Paper positions and real
orders remain disabled. Formal Data Shadow is still NO-GO.
