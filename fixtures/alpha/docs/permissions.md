# Scope and local approval

Only the configured alpha document directory and alpha issue records are exposed.
Beta issue identifiers, parent-directory paths, absolute paths and reparse-point files are denied.
The local reviewer can approve or reject an immutable proposed transition.
Approval is a workflow boundary, not authentication or an operating-system sandbox.
An owner with direct SQLite/filesystem access remains trusted.
