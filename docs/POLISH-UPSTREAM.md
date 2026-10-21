# Polish translation patch: submitting to Rockbox Gerrit

[Wersja polska](POLISH-UPSTREAM-PL.md)

Update 2026-10-21: the reviewed translation-only patch is now published as commit
`dcb4b6d60db9ae5052ba79cc8b80939539301d07` on the separate
[`polish-translation-fixes` branch](https://github.com/Pates2004/rockbox-accessible/tree/polish-translation-fixes).
It changes only existing Polish translations, not TTS code. GitHub confirms
Pates2004 as both author and committer. No Gerrit submission or official Rockbox
acceptance has occurred. The preparation paths/state below describe the original
2026-10-10 snapshot; do not blindly repeat its commit/push steps or overwrite
the published branch. The local reference checkout remains separate.

Status on 2026-10-10: the patch is prepared locally, but there is no contribution
commit or submission yet. You do not have a Rockbox Gerrit account. HiBy is
the current priority; keep this guide for later. None of the publication steps
described here was performed while preparing this documentation.

## 1. What is already prepared

- Patch: `D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch`.
- SHA256: `a5ba9d510ea56529eb17504cceb00191371a157d70fd227450437de2cbf7951c`.
- Separate checkout: `D:/work/Workspace/rockbox/polish-upstream-20261010/checkout`.
- Current branch: `polish-translation-fixes-20261010`.
- Base: `7d090f24b990ef54e3f9dc7eb2edba4865605471`.
- Only changed file: `apps/lang/polski.lang`; the patch is already applied,
  and the changes are unstaged and uncommitted.

The patch covers 47 existing IDs and 77 display or voice translation fields.
The resulting checkout's `git diff --numstat` reports 77 inserted and 77 deleted
lines; the raw patch file has 77/77 statistics. These are different
representations of the same change, not additional changed fields. It excludes the 101 new TTS/plugin
integration IDs, eSpeak code, HiBy and these guides. Preserve that scope.
The main tree, `D:/Rockbox/rockbox`, contains other unfinished work; prepare
the future submission in the separate checkout above. Do not apply the patch
again or create another checkout without a reason.

Read-only checks in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch'
Set-Location 'D:/work/Workspace/rockbox/polish-upstream-20261010/checkout'
git branch --show-current
git status --short
git diff --cached --name-only
git diff --numstat
git diff --check
git apply --reverse --check 'D:/Rockbox/rockbox/installfiles/polish-upstream/rockbox-polish-fixes-20261010.patch'
```

Expected results: the branch above, only ` M apps/lang/polski.lang`, an empty
index and `77 77 apps/lang/polski.lang`. The final two commands should succeed
silently. `--reverse --check` does not undo anything; it checks the already
applied patch. If the results differ, stop preparation and investigate;
do not reset or stash existing changes.

## 2. Official route and verification limits

[Rockbox CONTRIBUTING](https://raw.githubusercontent.com/Rockbox/rockbox/master/docs/CONTRIBUTING)
directs contributors to Gerrit code review. The official GitHub repository
currently has `has_pull_requests=false`, verified through the
[GitHub API](https://api.github.com/repos/Rockbox/rockbox). Neither a fork nor
an upstream pull request is needed for the Gerrit route described here.

The official
[.gitreview](https://raw.githubusercontent.com/Rockbox/rockbox/master/.gitreview)
confirms host `gerrit.rockbox.org`, SSH port `29418`, project `rockbox.git`
and target branch `master`. This is project configuration, not proof that
SSH authentication works for your account.

When checking [Rockbox Gerrit](https://gerrit.rockbox.org/) and the
[UsingGit](https://www.rockbox.org/wiki/UsingGit) and
[WhyRealNames](https://www.rockbox.org/wiki/WhyRealNames) wiki pages, the browsing
tool returned errors including 429, and direct HTTP returned an Anubis
protection page. Protection also replaced `config/server/info`, `ssh_info`,
the instance documentation and the hook file. HTTP 200 did not mean that the
requested content was received. Registration, login providers, permissions,
authentication configuration and this instance's HTTPS Git push URL have
not been verified.

The general mechanisms below were checked in Gerrit's official documentation:
[uploading changes](https://gerrit-review.googlesource.com/Documentation/user-upload.html),
[Change-Ids](https://gerrit-review.googlesource.com/Documentation/user-changeid.html)
and the [commit-msg hook](https://gerrit-review.googlesource.com/Documentation/cmd-hook-commit-msg.html).
Confirm the options supported by the actual server in its interface.

## 3. Account and identity: resolve before committing

When you choose to resume submission, open Rockbox Gerrit in a normal browser.
Check which official login or account creation method it actually offers.
Do not assume there is a Register form, GitHub login or automatic account
linking. If the real page or account access instructions are unavailable,
ask Rockbox maintainers for current instructions through the contact listed
on the official site. Further steps require a working account and permission
to upload changes.

There are two separate pieces of author information:

| Purpose | Required value |
| --- | --- |
| Rockbox contributor's full real name | Patryk Chojnacki |
| Git author and committer name | `Patryk (Pates2004)` |
| Git author and committer email | `255875083+Pates2004@users.noreply.github.com` |

Rockbox requires a full real name for contributions committed to Git too.
Putting the name in a profile or commit body is not a verified solution to
the difference from the required `user.name`. Before creating the commit,
ask maintainers whether they accept this combination with explicit credit
to Patryk Chojnacki. If they require a different Git identity, your explicit
decision is needed; do not change it automatically.

The GitHub noreply address is not an inbox for a verification link. It has
not been established whether Gerrit can associate it with the account or
accept a commit using it. Do not replace it without your explicit decision.
Your Gerrit username does not have to be `Pates2004` either.

Once those questions are resolved, the following **Git Bash** commands set
the identity only for the separate checkout. Run subsequent Bash blocks in
the same session, checking the result of each step:

```bash
cd /d/work/Workspace/rockbox/polish-upstream-20261010/checkout
git config --local user.name "Patryk (Pates2004)"
git config --local user.email "255875083+Pates2004@users.noreply.github.com"
git config --show-origin --get user.name
git config --show-origin --get user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Check author and committer separately: environment variables can override
Git configuration. If either name or email differs, stop before committing.
GitHub identity association does not grant Gerrit permissions. If you later
publish the commit on GitHub too, separately verify that both author and
committer are associated with `Pates2004` there.

## 4. Choose an actually available connection method

SSH and HTTP/HTTPS are Gerrit capabilities; servers do not necessarily expose
both. Choose one route that Rockbox offers for your account.

### SSH, if available

Confirm the username, host and port in the Gerrit interface. If the account
offers SSH keys, associate only your **public key** following its current
instructions. Do not overwrite an existing key. Never share a private key
or its passphrase.

After that setup, this example checks the connection. Replace
`YOUR_GERRIT_USERNAME` with your confirmed username; do not put a password in
the command. On the first connection, verify the host key fingerprint against
a trusted Rockbox source before accepting it.

```bash
GERRIT_USER='YOUR_GERRIT_USERNAME'
ssh -p 29418 "${GERRIT_USER}@gerrit.rockbox.org"
```

Gerrit may confirm authentication and then close the connection because it
does not provide an interactive shell. A login failure or access denial
does not confirm that uploading is ready.

### HTTP/HTTPS, if available

Copy the **authenticated Git URL for uploading changes** from the Rockbox
project interface. Do not guess its path from the web address, an anonymous
clone URL or another server's example. Use HTTPS when sending credentials.

Depending on configuration, the server may use a separate HTTP password or
token, or another specified method. Use only the option actually available
for your account. Do not assume a Generate Password button exists or that
the web password also works for Git. Enter secrets through a trusted
authentication prompt, never in a URL, command history, change description,
logs or a message to the assistant.

## 5. Official hook for generating a Change-Id

Before the first commit, install Rockbox's official `commit-msg` hook from
its server. A `Change-Id` identifies a Gerrit review; it is not a commit SHA.
These examples apply to the existing separate checkout with a regular `.git`
directory. Check configuration first:

```bash
git config --show-origin --get core.hooksPath
git config --show-origin --get gerrit.createChangeId
git config --show-origin --get gerrit.reviewUrl
test ! -e .git/hooks/commit-msg
```

An unset `--get` setting produces no output and exit code 1; that alone is
not an error. If `core.hooksPath` is set or a hook already exists, determine
the right location and preserve its function before installation; do not
overwrite it blindly. `gerrit.createChangeId=false` disables generation.
In newer hooks, `gerrit.reviewUrl` can replace a `Change-Id` trailer with a
`Link` trailer; do not assume Rockbox supports that variant. Resolve those
settings before continuing.

Choose **one** download method, only after the relevant service works.
SCP example after confirming SSH authentication:

```bash
scp -p -P 29418 "${GERRIT_USER}@gerrit.rockbox.org:hooks/commit-msg" .git/hooks/commit-msg
```

HTTPS alternative from the official endpoint, once it returns the real script:

```bash
curl --fail --location --proto '=https' --proto-redir '=https' --output .git/hooks/commit-msg https://gerrit.rockbox.org/tools/hooks/commit-msg
```

While preparing this guide, the HTTPS endpoint returned **anti-bot HTML**.
Do not download it now as a working hook. After a future download, read the
file and verify that it is the official `commit-msg` shell script rather
than HTML or an error message. Only then run:

```bash
chmod u+x .git/hooks/commit-msg
```

Do not execute a random script, invent an ID by hand or copy another commit's
Change-Id. If the file is wrong, stop before committing and obtain the correct
hook through an official route.

## 6. Human review, provenance and the first commit

Passing tests does not replace translation review. Read the entire patch and
justify each wording choice. Under `docs/CONTRIBUTING`, disclose AI assistance,
tools and confirmed models used, and be prepared to explain the changes.
Rockbox warns that AI-generated code is unlikely to be accepted; provenance
disclosure does not guarantee review or acceptance of the translation.

Not all models used for historical edits have been confirmed. State that gap
honestly instead of attributing the whole patch to the current documentation
session's model. Do not claim human review, listening, device testing or NVDA
testing until actually performed. Distinguish earlier catalog validation
results from checks repeated before submission. If required provenance is
still unresolved, discuss it with maintainers before publication.

After resolving those questions and completing review, stage only the language
file:

```bash
git diff -- apps/lang/polski.lang
git diff --check
git add -- apps/lang/polski.lang
git diff --cached --name-only
git diff --cached --check
git diff --cached -- apps/lang/polski.lang
```

The index must contain only `apps/lang/polski.lang`. If upstream has moved
since the stated base, first check compatibility with current `master`,
resolve any conflicts in the separate checkout and repeat appropriate catalog
checks. Do not publish unrelated commits or the larger integration.

Create one commit with `git commit`, writing an English description in the
editor. This text is a **template to complete**, not a ready-made declaration
of review or testing:

```text
lang: fix Polish translations

Correct existing Polish display and voice translations in polski.lang.

Contributor real name: Patryk Chojnacki
AI provenance: [verified tools/models for this patch and any unknown history]
Human review: [strings and meanings actually checked by a person]
Validation: [actual commands, results and remaining limitations]
```

Do not add invented `Co-authored-by` credit or a `Signed-off-by` declaration
whose meaning has not been confirmed. The hook should add a `Change-Id: I...`
line in the footer. After committing, check:

```bash
git log -1 --format=fuller
git show --format=fuller --stat HEAD
git show --format= --name-only HEAD
git log -1 --format=%B
git status --short
```

Author and committer must use the required name and email; the diff must
cover only the language file, and the message must contain completed
provenance and exactly one appropriate Change-Id. If the hook did not run,
fix its installation and use `git commit --amend` before uploading; check
the entire message again.

## 7. Upload for review when you choose to resume

This is the public step. Recheck identity, permissions, provenance and scope
before it. Uploading to `refs/for/master` creates a review; it does not mean
the patch has been merged into Rockbox. Do not push directly to `master`.

For the confirmed SSH route:

```bash
git push "ssh://${GERRIT_USER}@gerrit.rockbox.org:29418/rockbox.git" HEAD:refs/for/master
```

Or for the confirmed HTTPS route, after replacing the entire placeholder
with the Git URL from Rockbox's interface, without a password or token:

```bash
GERRIT_PUSH_URL='PASTE_VERIFIED_HTTPS_GIT_URL'
git push "$GERRIT_PUSH_URL" HEAD:refs/for/master
```

Open the change URL returned by the server. Check the project, `master`,
files, author, committer and description. Record the URL and review number
so you can return to it. Authentication or email verification failures need
investigation, not a random replacement author address or shared secrets.

## 8. Responding to review and uploading revisions

Reply in the existing review. For corrections to the same change, edit the
file in the same checkout, repeat appropriate checks, verify identity and run:

```bash
git add -- apps/lang/polski.lang
git diff --cached --check
git diff --cached --name-only
git commit --amend
git log -1 --format=fuller
git log -1 --format=%B
```

Preserve **the same Change-Id**, project `rockbox.git` and branch `master`,
then repeat the chosen `git push ... HEAD:refs/for/master` command. Gerrit
should add a new patch set to the existing review; confirm this in its UI.
The commit SHA may change after amend or rebase. Do not create a new commit
with a new Change-Id or a new review for each comment. Preserve the ID during
any rebase too. Merging depends on review and maintainer permissions, not
merely a successful push.

## What remains unverified

This guide is not a login, registration, email association, working-hook
download or submission test. Those steps remain for later, along with
agreement on the full name and required Git identity and final human review.
No new builds, listening, hardware or NVDA tests were performed. The existing
patch and separate checkout remain available for further work, without any
obligation to submit them now.
