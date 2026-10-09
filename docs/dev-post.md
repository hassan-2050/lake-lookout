---
title: "Lake Lookout: be the eyes the satellites lacked"
published: false
tags: devchallenge, hf26challenge, ai, opensource
---

<!--
DRAFT for the DEV Hacktoberfest Open-Source AI Challenge, Week 1 ("Touch Grass").
Paste into the challenge's submission template. Sections marked TODO-OUTING
are filled after the real outing; everything else is written from what the
repo measured. Do not publish with any TODO left in.
-->

*This is a submission for the [Hacktoberfest Open-Source AI Challenge: Week 1](https://dev.to/challenges/hacktoberfest-week1-2026-10-05) (Touch Grass). Prize category: Best Use of Gemma.*

## The lake nobody was looking at

On 16 August 2024, Thyanbo Tsho, a small glacial lake above the village of
Thame in Nepal's Everest region, burst. The flood reached Thame 22–25 minutes
later, damaging homes, the school and the health post and displacing 135
people.

In August this year I built a separate project that screened Himalayan glacial
lakes from free satellite images. Its most uncomfortable finding wasn't about
the models; it was about the sky. In the pre-event satellite record for the
four events it studied, **only 1 of 16 scenes got past the cloud-and-snow
quality filter**. The monsoon hides these lakes exactly when they fill.

People walk past them all the time: trekkers, guides, porters, herders. They
just don't write down what they see in a form anyone can use.

## What I built

**Lake Lookout turns a day's hike into a glacial-lake field log, with a model
that runs on your laptop and never touches the internet.**

- **On the trail** you only use your phone's camera and voice recorder. At each
  lake you take one wide photo and say what you see, for 10–30 seconds. The
  screen stays in your pocket.
- **In the evening**, at the teahouse or at home, with no signal, you copy the
  files to a laptop and run one command. **Gemma 4** (via Ollama) transcribes
  each voice note, reads each photo, and fills in a field checklist drawn from
  published glacial-lake hazard indicators. Examples: is glacier ice touching
  the water? Are there icebergs? Is the lake held back by a loose moraine
  ridge? Are there fresh rockfall scars above it?
- **You get** one offline page with your route, photos, words and checklist,
  plus a CSV and a GeoJSON file a researcher can load directly.

Every answer is *yes*, *no* or *unclear*, and every yes or no has to name its
evidence: what's in the photo, or what you said.

It deliberately does **not** produce a risk score or an alert. It records
observations for people qualified to interpret them.

## Demo

<!-- TODO-OUTING: embed the demo video (outdoor footage + running it + the page).
     And/or link the GitHub Pages copy of the real day's trip.html. -->

Code: <!-- TODO: GitHub URL -->

## Taking it outside

<!-- TODO-OUTING: where you went, how many stops, what the weather was, what
     you said into the phone, how long processing took on the laptop, what it
     got right, what it got wrong, and one moment that surprised you. Quote
     real numbers from the run. Keep it honest: a lowland pond coming back as
     "not glacial" is a correct result. -->

## The interesting part: making a small model unable to overclaim

Getting Gemma to answer a checklist took ten minutes. Getting it to answer
**only what it could actually see** took the rest of the day. I scored every
change against 11 freely licensed lake photos, hand-labelled. The set had seven
glacial lakes, one glacier with no lake, and three controls that aren't glacial
at all: a landslide lake, a reservoir and a village pond.

| version | change | accuracy | false "yes" | false "no" |
|---|---|---|---|---|
| v1 | answer, then evidence | 75% | 3 | 4 |
| v2 | evidence, then answer | 71% | 5 | **18** |
| v3 | "is the dam in view?" gates the dam questions | 82% | 4 | 5 |
| v4 | final | **88%** | **0** | **3** |

**v1:** the model kept answering "no" and then writing `"none"` as its
evidence. An unsupported "no" is the worst output a hazard log can have,
because it reads as "nothing there" and never looks like a failure. A small
rule-based verifier turns any yes or no without evidence into *unclear*.

**v2:** Ollama generates JSON fields in schema order, so I moved `evidence`
in front of `answer`. That forces the model to say what it sees before it
commits. Unsupported answers dropped to zero... and false "no" answers jumped
from 4 to 18. Now it wrote, with evidence, things like *"no visible seepage
through the dam"* about dams that were **behind the camera**.

**v3** made the scope explicit. Two questions now come first: *is the dam or
outlet in view?* and *is the land downstream in view?* The verifier won't let
the model claim anything about the dam or the valley below unless that part is
confirmed in view, or the hiker said it. False "no" answers fell to 5. When the
model isn't sure about the scope, it fails safe: the answer stays *unclear*.

Then the voice notes broke it in a new way. Given a photo **and** a voice note
together, the model stopped looking at the photo. It also quoted one sentence,
*"a long ridge of loose rock between the lake and the glacier"*, as the
evidence for six unrelated answers, including "no fresh rockfall". So now:

- the photo and the voice note are asked about **separately** and merged;
- when they **disagree**, the log shows both and marks the item *unclear*
  instead of picking a side;
- voice evidence has to actually appear in the transcript, and has to mention
  something the question is about.

None of these rules needs a bigger model. They're about forty lines of plain
Python, and each one exists because a measurement showed the failure it
prevents.

## Why open matters here

**The place has no signal.** Above the tree line in the Himalaya there's often
no mobile data for days. A cloud API is useless exactly where the lakes are.
Lake Lookout runs entirely on the laptop, and it enforces that: while it
processes a day, every network connection except the one to the local model
raises an error.

**The data shouldn't leave.** A field log is a list of exact coordinates of
lakes, trails and villages, plus a person's voice. With an open-weight model
running locally, none of it goes to a server I don't control.

**It costs nothing per run, and it runs without a GPU.** On my desktop's GPU,
`gemma4:e4b` takes about 2.4 s per photo. With the GPU turned off,
`gemma4:e2b` takes about 20 s per photo, roughly three minutes for an 8-stop
day on a CPU. A laptop chip will be slower, but it's still an evening task,
not a cloud bill.

**I could swap models and measure them.** I ran the same 11 photos through
three local models:

| model | accuracy | false "yes" | false "no" | per photo (GPU) |
|---|---|---|---|---|
| gemma4:e4b | 88% | 0 | 3 | 2.4 s |
| gemma4:e2b | 85% | 1 | 7 | 1.6 s |
| gemma3:4b (v3 prompt) | 65% | 7 | 4 | not comparable* |

The 4B-class Gemma 4 model is the default because it made the fewest false
"no" answers in every run. The 2B-class model is the default on CPU.

\*Another program held most of the GPU's memory during that run.

**One small open model does the whole job.** Gemma 4's E2B and E4B models take
audio *and* images. The same local model transcribes the voice note, reads the
photo, and returns schema-constrained JSON. There's no separate speech model to
install and no second runtime.

## Honest limits

- **Small evaluation.** 11 photos, labelled by me with an AI assistant's
  first draft. Scores move a few points between runs even at temperature 0, so
  treat small differences as noise.
- **Scope questions are the weak spot.** The model is poor at judging whether
  the dam is in view (24–41%). The gate fails safe, so a wrong "not in view"
  costs answers rather than producing false ones.
- **Voice in other languages.** Gemma 4 handled English well in testing.
  <!-- TODO-OUTING: say what happened if you recorded in Urdu or Nepali. -->
- **It's not a hazard assessment, and it won't become one by adding a score.**

## How I built it

Python, Pillow, ffmpeg and Ollama, with Gemma 4 E2B/E4B. I built it with
Claude Code as my coding agent. The `eval/results/` folder is the actual loop
we worked in: hypothesis, change, measured result. The commit history shows the
project going from an empty folder to this during the challenge week.

The satellite project mentioned at the top is earlier, separate work; it's the
reason this one exists, not part of it.

<!-- TODO: link to the repo again, licence (MIT), and the photo attributions
     (eval/photos/ATTRIBUTION.md). -->
