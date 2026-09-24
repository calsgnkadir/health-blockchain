# ADR 0003: One access policy for every record endpoint

## Status
Accepted.

## Context
Who may see a client's record used to be decided separately in each endpoint:
the record list in `core/cqrs/queries.py`, and a copy of the rule in each
single-record endpoint in `backend/routers/records.py`. The copies drifted apart:

- `GET /records/{client}/{block}` checked only that a client stayed in their own
  file. **Any practitioner could read any client's unprotected records, with no
  consent, by walking block numbers** (an IDOR). The list hid those same records.
- A practitioner could add records to any client's file without consent.
- Chain status and notifications were open to any practitioner.
- The Merkle proof endpoint checked nothing for a practitioner.

There was also a gap in the model itself. "private" means client-only, so a
therapist's process note — their own reflections, not meant for the client —
could only be stored as shared (the client sees it) or private (the therapist
who wrote it cannot see it).

## Decision
All rules live in one module, `core/services/access_policy.py`, as pure
functions (`can_view`, `can_view_stored`, `can_create`). Every endpoint that
reads or writes a record calls it; no endpoint re-implements it.

**File level.** A client opens only their own file. A practitioner opens a
client's file only while holding *some* active consent from that client.
Without one, every endpoint answers `403 No active consent from this client.`
— the same answer for a client who does not exist, so client IDs cannot be
probed.

**Record level.** Each record has an access level:

| Level               | Client | Practitioner                          |
|---------------------|--------|---------------------------------------|
| `doctor_shared`     | yes    | with consent for the record's type    |
| `private`           | yes    | never                                 |
| `practitioner_only` | never  | only its author, and with consent     |

- An unknown level (such as the old `admin_only`) is closed, never read as shared.
- A password-protected record's type is unknown until it is decrypted, so a
  practitioner needs consent for **all** records to see it at all. Its audience
  (access level and author) is kept outside the ciphertext, so a locked
  client-only record is not even listed for the practitioner, nor a locked
  practitioner-only note for the client. (Before this, a practitioner with
  consent for all records saw a client's locked journal as an "ENCRYPTED
  RECORD" row.) The audience is not part of the signed block: changing it can
  only change which placeholder is listed, never what is decrypted — the real
  level inside the ciphertext is checked again after decryption.
- Chain bookkeeping blocks (genesis, audit, correction wrappers) are not shown
  to practitioners.
- A record the user may not see gets `404`, as if it did not exist — the list
  leaves it out rather than showing it locked.

**Writing.** A client may create `doctor_shared` or `private` records; a
practitioner `doctor_shared` or `practitioner_only`, and only with consent for
the record's type. A correction must pass both checks: the user can see the
original, and could create the corrected version (so a correction cannot move
a record to a type the practitioner holds no consent for).

**Notifications** are messages to the client and only the client reads them.

Administrators, auditors and security officers are outside this policy: they
may read a client's records only with a dual-control co-signature, checked by
the routers before the policy is consulted.

## Consequences
- **Positive:** one place to read, review and test the rules
  (`tests/test_access_policy.py` needs no database). The API tests in
  `tests/test_practitioner_file_access.py` fail against the old code.
- **Positive:** revoking consent closes the whole file at once, the
  practitioner's own notes included.
- **Negative:** a practitioner's own `practitioner_only` notes also disappear
  when consent is revoked. This is deliberate — the notes are part of the
  client's file — but a practice may want its own archive later.
- **Negative:** the stored values keep their old names (`doctor_shared`,
  `private`) so existing chains still load; only the labels changed.
