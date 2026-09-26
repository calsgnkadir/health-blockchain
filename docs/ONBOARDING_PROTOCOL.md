# Onboarding: how accounts come to exist

Nobody registers themselves in Mahrem. Every account starts **pending**, with a
random password nobody knows, and becomes usable only when its holder redeems a
**single-use code** that reached them outside the system (in person, or by a
channel the practice trusts). Login is refused for any account that is not
`ACTIVE_ENROLLED`.

There are three ways an account is created.

## 1. A practitioner invites a client

This is the everyday path (`backend/routers/onboarding.py`).

1. The practitioner opens **My Clients** and enters the client's name.
2. The system picks the next free client ID (`CL-###`). An ID whose record chain
   still exists — for example, from a deleted account — is never handed out again,
   so a new client can never inherit someone else's records.
3. A pending client account is created (username = the ID in lower case) and an
   invitation code is returned **once**. The code is valid for 72 hours and only
   its SHA-256 hash is stored, so it cannot be looked up later.
4. The practitioner gives the client the code, or a link with the code in the URL
   fragment (`/#invite=…`). Browsers do not send the fragment to the server, so the
   code does not land in access logs; the page removes it from the address bar.
5. The client chooses a password and the account becomes `ACTIVE_ENROLLED`.

**The invitation grants no access.** The practitioner cannot see the new client's
file until the client gives consent on the Consent page. The client is only told
who invited them, so they know whom to give it to.

Limits: a practitioner sees only the clients they invited, can issue a new code only
for their own pending clients (the old code stops working), and may hold at most 20
open invitations.

## 2. A practitioner invites a secretary

A practitioner can invite the secretary who will run their appointment book
(`POST /api/v1/onboarding/invite-secretary`, "My Clients" page). The account
starts pending, with the same single-use 72-hour code, and is linked to that
practitioner. A secretary sees that practitioner's appointments — clients'
names, IDs and times — and no record, consent or note.

## 3. An operator provisions a staff account

Practitioners, administrators, auditors and security officers are created by an
administrator or security officer (`POST /api/v1/onboarding/provision`) after their
identity has been checked outside the system. The same rules apply: a pending
account, a single-use 72-hour code stored as a hash, and no login until the code is
redeemed.

## After sign-in: passkeys

Any account can then register a passkey (FIDO2 / WebAuthn). With
`MANDATORY_FIDO2=true`, for every role:

- an account that has a passkey **must sign in with it** — its password alone is
  refused (checked before the password, so the answer never confirms a guess);
- an account without one may sign in with its password and is taken straight to
  passkey enrolment. Refusing that login would lock a new account out for good,
  because a passkey can only be enrolled by someone who is signed in.

## Rate limit

Redeeming a code shares the sign-in limit: 5 attempts per IP per minute.
