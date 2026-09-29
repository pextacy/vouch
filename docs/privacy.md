# Vouch — privacy

Vouch is an Anna App. It runs inside your Anna account and has no server of
its own. This page describes what it does with the things you give it. Every
statement here is a description of the code in this repository; if the code
changes, this page changes with it.

## What Vouch stores, and where

Everything Vouch keeps is written to your Anna account's app storage
(`storage.*`, scoped to this app and to you). Nothing is written anywhere else.

| What | Stored as | Kept until |
|---|---|---|
| Your CVs — split into numbered lines, including lines you add or edit, and the file name | `cv:v1` (one key per CV) and the list of them in `cvs:v1` | You delete the CV or use *Delete all my data* |
| Your applications — the posting, the requirement map, tailored bullets, letters, answers, notes and status | `match:v1:<id>`, indexed in `matches:index:v1` | You delete it, or it falls out of the newest 300 |
| App settings — language, theme, whether you have seen the introduction, and when you first opened the app | `profile:v1` | Removing Vouch from your account |

Deleting a CV deletes the applications made against it; the confirmation says
how many.

## What Vouch does not store

- **Uploaded files.** A PDF or DOCX is held in memory only for as long as it
  takes to split it into lines, then dropped. An upload you abandon is dropped
  after ten minutes. It is never written to disk.
- **Documents you check.** A CV or letter pasted into *Check a document* is
  read once and written nowhere.
- **Logs of your content.** The engine logs counts and error codes, never a
  line of your CV or a posting.

The engine keeps one thing in memory between requests: the requirements it
extracted from a posting, so that checking the same posting twice does not
spend your credits twice. That cache lives only in the running process, is
never written to disk, and is cleared by *Delete all my data*.

## Who sees your data

- **The model.** To read a posting and write bullets, letters and answers,
  Vouch asks the model through Anna's own sampling channel. It sends the
  numbered lines of your CV and the posting. It has no API key and calls no
  model provider directly; Anna's terms govern that request.
- **Job posting links.** If you paste a link instead of a posting, Anna fetches
  that page for Vouch. Only the link is sent; nothing of yours goes with it.
- **Nobody else.** Vouch calls no analytics, tracking or third-party service,
  and its window loads nothing from outside Anna.

Sharing is always something you do. *Copy summary* and *Make a card* produce
text and an image built from counts alone — no CV line, no employer and no
wording from the posting. The role title appears on the card only if you add
it.

## Deleting your data

*Your data → Delete all my data* removes every CV and every application from
storage and tells the engine to drop anything it is still holding in memory, in
one step. It keeps the settings record, which holds nothing you wrote — only
your language and theme, so the app does not greet you with the introduction
again. You can download your CV first from the same screen.

## Contact

Questions about this page go to the support link on the Vouch listing.
