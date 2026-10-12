# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:               |

Only the latest `0.1.x` release receives fixes. Nothing before `0.1` was ever
published as a tag, so there is nothing older to keep alive.

## Reporting a vulnerability

Please report a suspected vulnerability privately, through GitHub's private
vulnerability reporting for this repository:
<https://github.com/annaputilovskaya/quackend/security/advisories/new>
(the **Security** tab → **Report a vulnerability**).

If that channel is unavailable, contact the maintainer through their GitHub
profile (<https://github.com/annaputilovskaya>) instead of opening an issue.
Never put exploit details in a public issue, a pull request or a chat; a report
that is already public cannot be fixed quietly.

Useful to include:

- the quackend version, Python version and operating system;
- the spec (or the smallest fragment of it) that triggers the problem;
- the exact command that reproduces it;
- what an attacker or an untrusted input could achieve with it.

The maintainer will acknowledge the report, say whether it is accepted, and
keep the discussion private until a fix is released. Once the fix is out, the
advisory may be published and the issue opened publicly, credited to the
reporter unless asked otherwise.

## What is worth reporting

quackend serves generated mock data from a local spec, so the interesting
surface is the untrusted **input**: a spec that crashes the server, request
bodies that are not handled as documented, and paths that make the mock answer
something other than what the spec declares.

Not vulnerabilities: the mock answers fake data, it holds no real user data, and
it binds `127.0.0.1` unless you pass `--host`. Do not expose a quackend instance
to a network you do not trust.

## CORS

The mock answers every `Access-Control-Allow-Origin` with `*`: it is a throwaway
mock a browser front end calls directly, not a backend that holds a session, and
a single wildcard is the only policy that works without per-origin setup. This is
deliberate. It is also why the built-in API docs are disabled — the mock exposes
no schema surface to browse — and why the mock binds `127.0.0.1` by default; do
not run it with `--host 0.0.0.0` on a network you do not trust.
