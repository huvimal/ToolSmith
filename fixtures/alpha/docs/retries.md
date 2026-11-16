# Retry policy

Read operations may be retried after a transient transport failure.
Mutation proposals use an explicit idempotency key and canonical payload hash.
Applying the same approved action again returns its stored result without another issue update.
Reusing a key for a different change is a conflict, not a new action.
Expired approval requires a new proposal; never silently extend it.
