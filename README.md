# Fantabasket Progettone

A private, self-hosted set of Telegram bots that runs the day-to-day management of
**one fantasy NBA league played among friends**: 24 teams, split across two Yahoo
Fantasy Basketball leagues because Yahoo caps leagues at 20 members.

This is a non-commercial hobby project. It has no public users, no website and no
app store presence: the only people who interact with it are the members of our
league.

## What it does

Our league uses a "dynasty" ruleset that goes well beyond what Yahoo handles
natively, so for years it has been run by hand on a shared spreadsheet. These bots
automate that bookkeeping:

- **Contracts and salary cap**: multi-year contracts, cap and salary floor checks,
  dead money from releases.
- **Free agency auctions**: timed auctions in a Telegram channel, including
  restricted free agency (RFA) with matching rights.
- **Trades**: proposal, validation (cap, roster limits, draft-pick rules) and
  approval flow.
- **Draft and rookie scale**: draft picks, rookie rights and rookie-scale contracts.
- **League sheet sync**: keeps the league's Google Sheet (rosters, picks) up to
  date via Google Apps Script.
- **Roster cards**: rendered roster images (Typst) posted on request.

## Architecture

Everything runs with Docker Compose on a small home server.

```
                ┌──────────────┐     ┌──────────────┐
 Telegram ◄────►│   bot-main   │     │   bot-aste   │◄────► Telegram
                └──────┬───────┘     └──────┬───────┘
                       │                    │
          ┌────────────┼──────────┬─────────┘
          ▼            ▼          ▼
   ┌────────────┐ ┌──────────┐ ┌──────────────┐
   │ PostgreSQL │ │gas-router│ │ yahoo-router │
   └────────────┘ └────┬─────┘ └──────┬───────┘
                       ▼              ▼
              Google Apps Script   Yahoo Fantasy API
              (league sheet)       (read-only)
```

| Service        | Role                                                            |
|----------------|-----------------------------------------------------------------|
| `bot-main`     | League management bot (contracts, trades, draft, rosters)       |
| `bot-aste`     | Free agency / RFA auction bot                                   |
| `gas-router`   | Internal proxy to the Google Apps Script web app                |
| `yahoo-router` | Internal proxy to the Yahoo Fantasy API (OAuth2, token refresh) |
| `postgres`     | League database                                                 |

The routers are only reachable on the internal Docker network. Credentials are
stored as Docker secrets and are never committed to this repository.

## Yahoo Fantasy data usage

`yahoo-router` is the only component that talks to Yahoo. Its scope is
deliberately narrow:

- **Read-only.** No write access is requested or needed.
- **Two leagues only.** The two private leagues that make up our group, both of
  which the author is a member of. No other leagues or users are queried.
- **Minimal data.** League teams, team rosters and players' eligible positions.
  Eligible positions matter because our ruleset requires each player's role to be
  one of the positions Yahoo lists for him.
- **Low volume.** Roughly one refresh per day, cached locally.
- **Private.** Data is shown only to the members of these two leagues, in our
  Telegram group and our league spreadsheet. It is not published, redistributed,
  sold, or used to train AI models.

Current status: OAuth and league/team lookup are implemented; roster and position
sync are planned.

### What ends up in the league spreadsheet

The Google Sheet is our league's own ledger, and almost none of it comes from
Yahoo. Per team it contains:

- players under contract, with **salary and years left** (our league's contracts,
  not Yahoo data);
- each player's **league role**, chosen by the team manager among the positions
  Yahoo lists for that player (this is the only Yahoo-derived field);
- dead money from released players, injury exceptions, cap penalties and rule
  counters (free releases, role changes used);
- draft picks, unsigned draft rights and rookie-scale contracts.

No Yahoo stats, scores, projections or rankings are stored or shown anywhere: the
fantasy averages our rules need are computed from Basketball-Reference (see below).

## Other data sources

- **Basketball-Reference**: daily season averages, used to compute each player's
  fantasy average with our league's scoring formula (minimum salaries, renewals,
  free agent lists).

## Tech stack

Python 3.12 · python-telegram-bot · PostgreSQL 16 · FastAPI · Typst ·
Google Apps Script · Docker Compose

## Disclaimer

Not affiliated with, endorsed by, or sponsored by Yahoo or the NBA. All trademarks
belong to their respective owners.
