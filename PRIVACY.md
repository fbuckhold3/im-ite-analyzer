# Privacy and data handling

ITE score reports, rosters and MKSAP exports are education records about identifiable residents.
This software is designed so that it never needs to keep them.

**What the app does with your files**
- Files you upload are read into memory for your session only and discarded when the session ends. The web
  framework briefly writes each upload to a temporary file; the app deletes it immediately after reading it.
- The app does not write uploads to disk, store them in a database, log their contents, or send them to any other service.
- The app uses no analytics, tracking cookies, or third-party scripts that receive your data.
- Downloads (reports, crosswalks) are generated in memory and sent only to you.

**What you are responsible for**
- Program directors: follow your institution's policies (e.g. FERPA in the U.S.) for sharing and storing
  the reports you download. The identified PD report contains resident-level data; the program summary
  is aggregate-only.
- Residents: your own report is yours. The app does not share it with your program.
- Whoever hosts an instance of this software is responsible for its hosting environment
  (authentication, access logs, TLS). The reference deployment runs on Posit Connect Cloud.

**This repository** contains no resident or program data. Tests use invented names and IDs.

Questions or concerns: open a private report via GitHub's "Report a vulnerability"
(see [SECURITY.md](SECURITY.md)).
