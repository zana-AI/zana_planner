# Clubs & Challenges — the product model

Status: **decided** · Owner: Javad · Date: 2026-08-17

Supersedes the entity model in `CHALLENGES_DESIGN.md` (§3, §4) — that doc's *content*
layer (decks → items → attempts) stands; its treatment of a challenge as a top-level
entity does not. Product rationale in `memory/project-vocab-challenges-direction.md`.

---

## 1. Why this doc exists

"Club" had been doing two incompatible jobs, and the mismatch was the root of several
concrete failures:

- **Cheenva** — 6 friends who already knew each other. The group works. Chat is a real
  part of the value.
- **French with Atena** — hundreds of channel subscribers who don't know each other. The
  same *shape* (a Telegram group where everyone talks) was applied, and it did not work.

A group of strangers past ~10 people degrades: people show up to socialise rather than to
do the activity, most lurk, and beyond sharing results and clapping there is no
interaction worth designing for. That isn't a content problem or an LLM-quality problem —
it's a container problem. A cohort doesn't need a room.

## 2. The two shapes

### Shared ledger (small, peer)
2–8 people who **actually do the activity together** — a couple going to the gym, a few
friends playing the same daily game. The commitment is mutual and pre-existing; Xaana
doesn't create the social glue, it keeps the books.

Value = *shared memory of a shared commitment*. Reminder → check-in → history, visible to
everyone in it. Works at n=2. Degrades past ~8, because "we do this together" stops being
literally true.

The Telegram group stays for these — it's where the commitment already lives.

### Cohort (large, creator-led)
One coach/creator, many subscribers who don't know each other. Value = the creator's
content + my own progress + not feeling alone.

**No Telegram group.** The funnel is the creator's existing channel → their Xaana page.
Everything else is DM + Mini App. This sidesteps group dynamics rather than trying to
moderate them.

## 3. One entity, not two

Club and challenge are **two time scales of the same thing**, not two entities:

- **Club** — the durable place. Name, public page at `xaana.club/<handle>`, members,
  leaderboard, history, streaks. This is what you join.
- **Challenge** — what's due **today** inside a club. One round.

What actually varies between cases is three *independent* switches, none of which justify
a separate entity:

| | Cheenva | Gym (2 people) | Atena |
|---|---|---|---|
| Today's round carries content in Xaana? | no (external game) | no | **yes** (quiz deck) |
| Telegram group attached? | yes | yes | no |
| Coach-led or peer? | peer | peer | **coach** |

Every combination is legitimate, including ones not yet built (a coach with 5 students; a
groupless public challenge with no coach). Modelling club and challenge separately would
mean duplicating streaks, leaderboards, check-ins and reminders across both and
reconciling them forever.

This is already half-true in the code: `actions_repo.append_scored_checkin()` writes a
quiz score onto a `club_checkin` action specifically so the existing streak and
leaderboard paths pick it up. Atena's results already flow through Cheenva's machinery.

### Consequence for the schema

`clubs` is the identity. The `challenges` table dissolves — its identity fields
(`title`, `host_user_id`, `description`, `visibility`, `source_key`, `status`) are the
club's fields under different names; what is genuinely challenge-specific
(`activity_type`, `cadence`) moves onto the club or the round. The content tree
(`challenge_decks` → `challenge_items` → `challenge_attempts`) **stays** — it has no
equivalent on the club side. A deck becomes *today's round for this club*.

Clubs whose rounds have no content (Cheenva, gym) simply produce a checkmark instead of a
score.

## 4. Clubs are adopted, not created

The app-side "create a club" flow required a **human Xaana admin** to create a Telegram
group and pass the details back (`telegram_status = 'pending_admin_setup'`). That cannot
scale past one person doing it by hand, and it was not used.

Replacement: **add @xaana_bot to a group you already have.** The club is adopted, not
created. This removes the admin bottleneck, kills the cold-start problem (no empty group
waiting for a reason to exist), and uses a gesture Telegram users already understand.

Cohorts need no group at all, so they need no creation flow either — a creator gets a page.

## 5. Public identity: `xaana.club/<handle>`

Mirrors Telegram's own namespace: if the channel is `t.me/french_with_atena`, the Xaana
page is `xaana.club/french_with_atena`. The creator makes zero naming decisions, the
mapping is self-evident, and ownership can be verified by checking the claimant is an
admin of that Telegram channel.

This replaces the `source_key` startapp-token funnel with something a creator can put in a
bio, a channel description, or say out loud.

Reserved top-level words are kept deliberately short (`api`, `admin`, …) — everything else
at the root is a handle, as on t.me.

The **public profile and the settings screen are different products** and must not share a
route. The public page is a landing page for a stranger arriving cold from a channel: who
this is, today's challenge, the leaderboard, a join CTA. The current club page is an
owner's management screen with destructive controls on it. (A bug from exactly this
confusion already shipped once: the group leaderboard button dropped ordinary members onto
the owner's management page.)

## 6. Leaderboards scale with size

The one thing that genuinely must differ by club size — and it's presentation, not model:

- **2–8 members who know each other** → flat list. Brackets would be absurd.
- **Hundreds of strangers** → flat ranking is meaningless and actively demotivating
  ("you are rank 214"). Needs Duolingo-style leagues: promotion/relegation within brackets
  of peers at a similar level. Social comparison *without* social interaction — no names
  you need to know, nothing to say, nobody to be creepy at.

Note the demotivation risk is real and already visible: a rendered Cheenva leaderboard
shows two active members and **four at 0%**, publicly, to people who know each other.

## 7. The bot's role inside a group

The bot as a *conversational participant* in group chat is being removed. Evidence from
the Cheenva history: it told a member it was not "a مربی حسابداری" (an accounting coach), a
non-sequitur the group openly mocked; it congratulated someone for finishing a game they
had not finished; it repeated near-identical «خوبه که…» praise several times in a row.
Outside of encouragement noise there was no value in it.

What stays in groups:

- **Scheduled posts** — the daily check-in card, the leaderboard image. Deterministic, no
  LLM in the group path.
- **Emoji reactions.** These consistently landed, and for a structural reason worth
  keeping in mind: generated text has *unbounded* failure modes (it can say something
  absurd and get mocked), a reaction has *bounded* ones (worst case, a slightly odd
  emoji). Keep the bounded-risk presence; delete the unbounded-risk one.

The AI coach keeps its place in **DMs**, where it is good and where the primary
bookkeeping use case lives.

Resulting split:

| Surface | Xaana's role |
|---|---|
| Group | scheduled posts + reactions. No LLM. |
| DM | the actual AI coach / bookkeeper. |
| Cohort | DM + Mini App. No group. |

## 8. Where the wedge is

Not "Duolingo for Persian" and not "async Kahoot" — **distribution**. A teacher with a few
hundred Telegram subscribers does not have to migrate their audience anywhere, and neither
Duolingo nor Kahoot can reach that audience without an app install and an account. Xaana
is already where those people are.

> Turn an existing Telegram channel into a daily-practice cohort, without asking anyone to
> install anything or talk to strangers.

The corollary is a hard product requirement: **the creator's marginal effort must be near
zero.** "Please author daily quizzes for us" is a job offer and it is why the first
attempt stalled; "we turn the posts you already write into a daily quiz" is a gift. Any
plan to onboard more coaches depends on automated ingestion being genuinely good, not on
recruiting more motivated teachers.
