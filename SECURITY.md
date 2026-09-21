# Security

GUMMY runs on your own machine and holds your memories, conversations, files
and goals in a local database. It can also read your repositories and, with
your approval, write files and run commands. That combination is the reason
this document exists.

## Reporting a vulnerability

Open a [private security advisory](https://github.com/Iqbalmeerajohn/GUMMY-OS/security/advisories/new)
rather than a public issue. Include what you did, what happened, and what you
expected — a reproduction matters more than a severity rating.

There is no bounty. This is a personal project, so expect a reply in days
rather than hours.

## The threat model this is built around

The interesting attacker here is not someone on your network. It is **text**.
GUMMY reads your documents, fetches web pages, and receives messages, and any
of those can contain instructions aimed at the model. So the design assumes
the model can be talked into asking for anything, and puts the limits
somewhere the model cannot reach.

**Tool arguments are untrusted.** A path, a URL or a command from the model is
treated the way you would treat form input. The boundary is never an argument:

- Host paths resolve through one function that checks containment against
  `GUMMY_WORKSPACE_ROOTS` *after* resolving `..` and following symlinks. With
  no roots configured, every host tool refuses everything. There is no tool
  parameter that widens the allowlist.
- `http_fetch` resolves each hostname to its IPs and refuses any that is not
  globally routable — loopback, private ranges, and link-local (which covers
  cloud metadata endpoints). Redirects are followed one at a time and
  re-checked, so a public host cannot bounce a request to `127.0.0.1`.
- `shell_exec` parses with `shlex` and executes an argv list. It is not a
  shell: pipes, `;`, `&&` and redirection are rejected rather than
  interpreted.

**Consequence is gated by tier, not by intent.** Every tool is Green (read-only,
runs immediately), Yellow (changes something, needs your approval) or Red
(irreversible, needs your approval for every single call, and no standing
allowance can cover it). Approving runs the call from the **stored preview** —
the exact arguments you read — never from the approve request, so an approval
cannot be redirected to a different action.

**Third-party tools do not grade themselves.** Tools discovered from an MCP
server arrive as Yellow unless you explicitly list them as Green in your own
config. They are namespaced so they cannot shadow a built-in, and the catalog
is sealed after startup, so a running process never gains a capability.

**Every invocation is audited.** Tier, decision, outcome and reason go to
`tool_invocations`, including approved actions. An action that cannot be
written to the trail is refused rather than performed.

## What is NOT protected

Stated plainly, because a security document that only lists strengths is
marketing.

- **`shell_exec` runs as you.** Approving one is equivalent to typing it
  yourself. The workspace root constrains where it *starts*, not where it can
  go. Read every command before approving it.
- **Protected filename refusal is a guard rail, not a boundary.** `file_read`
  and `file_write` decline `.env`, `id_rsa`, `*.pem` and similar by name.
  `shell_exec` does not consult that list at all. It stops an accident, not an
  attacker.
- **Prompt injection is mitigated, not solved.** A malicious document can
  still persuade the model to *propose* something. The tier system means you
  see the proposal. It does not mean the model was not fooled.
- **A hostile MCP server can write a persuasive tool description.** Tiering
  handles the consequence; nothing prevents the persuasion.
- **The local model is not a security control.** Never rely on the model
  declining to do something.
- **Auth is a single-user JWT setup.** Fine for a personal machine. It has not
  been reviewed for multi-tenant or hostile-user deployment.

## Deploying beyond localhost

The defaults assume loopback. If you expose GUMMY through a tunnel:

- Use a long password. The login page is then the only thing between the
  internet and your memory.
- Set `BACKEND_CORS_ORIGINS` to exactly your tunnel origin.
- Prefer the Telegram transport if you only need chat: it polls outbound, so
  nothing is exposed and no port is opened.
- Do not set `AUTH_DEV_BYPASS=true`. A startup guard refuses it when
  `APP_ENV=production`; do not work around that guard.
