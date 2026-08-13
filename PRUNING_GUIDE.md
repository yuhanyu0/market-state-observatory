# Pruning Guide

Complex research modules must be default-disabled, independently testable,
removable without changing stable schemas, documented in `labs/`, and activated
only by reproducible incremental evidence.

Remove or archive a lab when it has no owner, lacks point-in-time inputs, cannot
beat its transparent comparator, duplicates a stable module, or materially
raises maintenance/security cost without decision value. Removal must not alter
historical public certificates or private run hashes.

Current pruning candidates are Graph SSM, PDE/field models, and the semantic
event observer. All are disabled.
