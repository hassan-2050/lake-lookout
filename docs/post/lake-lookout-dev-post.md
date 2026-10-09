---
title: "Lake Lookout: Be the Eyes the Satellites Lack (Gemma 4, fully offline)"
published: false
description: Hike with your phone. In the evening, a local Gemma 4 turns your photos and voice notes into a glacial-lake field log, with no signal, no cloud and no risk scores.
tags: devchallenge, hf26challenge, gemma, opensource
cover_image: https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/cover.png
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge: Week 1](https://dev.to/challenges/hacktoberfest-week1-2026-10-05) (Touch Grass), entered for **Best Use of Gemma**.*

> **TL;DR:** Lake Lookout turns a hike past glacial lakes into a field log that
> researchers can use. On the trail you only take photos and short voice notes,
> and your phone stays in your pocket. That evening, with no internet, **Gemma 4
> runs on your own laptop**, listens to every voice note, looks at every photo,
> and fills in a checklist drawn from published glacial-lake hazard indicators.
> Every *yes* or *no* has to name its evidence. Anything it can't actually see
> stays *unclear*. It is open source (MIT), and it costs nothing to run.

![Lake Lookout: a processed day in Hunza with its route map, stats and stop cards](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/01-app.png)

## The lake nobody was watching

On 16 August 2024, Thyanbo Tsho, a small glacial lake above the village of
Thame in Nepal's Everest region, burst. The flood reached Thame about 22 to 25
minutes later. Homes, the school and the health post were damaged, and 135
people were displaced.

Earlier this year I built a separate project that screened Himalayan glacial
lakes from free satellite images. Its most uncomfortable finding wasn't about
models at all; it was about the sky. In the pre-event satellite record for the
four floods it studied, **only 1 of 16 scenes got past the cloud-and-snow
quality filter**. The monsoon hides these lakes exactly when they fill up.

People walk past them all the time, though: trekkers, guides, porters, herders.
Their eyes work under cloud. What they see just never gets written down in a
form anyone can use.

So, for a challenge called *Touch Grass*, I built the opposite of a dashboard
you stare at. **Lake Lookout makes the hiker the sensor, and keeps the screen
for the evening.**

## What I built

A day with Lake Lookout looks like this:

1. **On the trail.** At each lake, take one wide photo and record 10 to 30
   seconds of what you see: *"Grey milky water, a long ridge of loose rock
   between the lake and the glacier, ice on the far shore."* That's all. Your
   phone's own camera and voice recorder; no app, no signal.
2. **In the evening.** At the teahouse, the campsite or home, copy the files to
   a laptop and drop them into Lake Lookout. **Gemma 4** (E4B, through Ollama)
   transcribes each voice note, reads each photo, and fills in a field checklist
   for every stop. It uses the GPS and time already in the photos to rebuild
   your route.
3. **Share the log.** You get one offline page with your route, photos, words
   and checklist, plus a **CSV** and a **GeoJSON** file a researcher can load
   straight into a spreadsheet or a GIS.

The checklist asks what a hiker can actually see, and where a question
corresponds to a published hazard indicator, it says which one:

| Observation | Published indicator it corresponds to |
|---|---|
| Glacier ice touching the water | Rounce et al. 2016 (mother glacier within 600 m) |
| Icebergs or calving | Sakai et al. 2009 (calving onset) |
| Steep slopes or hanging ice above the lake | Fujita et al. 2013; Rounce et al. 2016 |
| Fresh rockfall or landslide scars above | Allen et al. 2019 (impulse-wave trigger) |
| Low freeboard (dam crest close to the water) | Mergili & Schneider 2011 |
| Steep outer dam face | Lv et al. 1999 (moderate confidence) |
| Water body · glacial setting · moraine dam · seepage · people downstream | plain field observations, labelled as such |

**It deliberately gives no risk score and raises no alert.** It records
observations for people qualified to interpret them. A wrong "this lake is
safe" is worse than no app at all.

## Demo

{% embed [YOUR_YOUTUBE_OR_LOOM_URL] %}

*The demo is the real app and the real local model. To show a realistic day, it
uses a test day I assembled from freely licensed Wikimedia photos of Hunza,
Pakistan, with synthetic voice notes; it is labelled as such in the repo.
Processing is sped up in the video. It took about 30 seconds on my machine for
7 stops. Even the narration is local and open: it is
[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), an open-weight
text-to-speech model running on the same laptop. I checked every line by having
Gemma 4 transcribe it back, which is how I found that the voice said "Alama"
for "Ollama".*

![Exploring a processed day: map, evidence, disagreements](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/lake-lookout-demo.gif)

**Code:** [https://github.com/[YOUR_GITHUB_USERNAME]/lake-lookout](https://github.com/[YOUR_GITHUB_USERNAME]/lake-lookout)

## Taking it outside

[WRITE THIS AFTER YOUR OUTING. Keep it concrete and honest. A short structure
that works:

- **Where and when:** "On [DAY], I walked [PLACE / ROUTE, about X km] and
  stopped at [N] spots by [the lake / pond / river / stream]." Say what the
  weather and light were like.
- **What I did at each stop:** one wide photo plus a voice note. Quote one
  voice note word for word: "[YOUR WORDS]".
- **The evening:** "Back home I copied [N] photos and [N] voice notes off my
  phone, pressed Process, and it took [X] seconds on [YOUR LAPTOP, GPU or
  CPU]."
- **What it got right:** [e.g. a pond came back "not glacial", as it should].
- **What it got wrong, or surprised me:** [one real example from your log].
- **How it felt:** [Did you look at your phone less? Did saying what you saw
  out loud make you look more closely?]

Add one or two photos from your walk and a screenshot of your own trip page:
![My outing](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/[YOUR_OUTING_SCREENSHOT].png)]

## The interesting part: making a small model unable to overclaim

Getting Gemma to answer a checklist took ten minutes. Getting it to answer
**only what it could actually see** took the rest of the build. A field log
with a confident wrong answer is worse than an empty one, so I treated this as
the real problem and measured every change.

I hand-labelled 11 freely licensed lake photos: seven glacial lakes, one
glacier with no lake in frame, and three controls that aren't glacial at all
(a landslide lake, a reservoir and a village pond). That gives 91 scored
answers per version. [LABEL REVIEW: replace this sentence with either "I
reviewed every label myself" or "My coding agent drafted the labels and I
spot-checked them".]

![Five measured versions: false "no" answers spike to 18 in v2 and fall to 3; accuracy rises from 75% to 87–88%](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/09-iterations.png)

| version | change | accuracy | false "yes" | false "no" |
|---|---|---|---|---|
| v1 | answer, then evidence | 75% | 3 | 4 |
| v2 | evidence, then answer | 71% | 5 | **18** |
| v3 | "is the dam in view?" questions | 82% | 4 | 5 |
| v4 | final prompt | **88%** | **0** | **3** |
| v5 | v4 plus bug fixes found on real photos | 87% | 0 | 3 |

**v1: the silent "no".** The model kept answering *no* and then writing `"none"`
as its evidence. An unsupported "no" is the most dangerous thing a hazard log
can say, because it reads as "nothing there" and never looks like a failure. So
a small rule-based verifier turns any yes or no without evidence into
*unclear*.

**v2: the fix that made it worse.** Ollama's structured output generates JSON
fields in the order the schema lists them. So I moved `evidence` in front of
`answer`, which forces the model to say what it sees *before* it commits.
Unsupported answers dropped to zero... and false "no" answers jumped from 4 to
18. Now it wrote, with a straight face and real evidence, *"no visible seepage
through the dam"* about dams that were **behind the camera**.

**v3: absence needs a view.** Two questions now come first: *is the dam or
outlet in view?* and *is the land downstream in view?* The verifier won't let a
photo claim anything about the dam or the valley below unless that part is
confirmed in view. If it isn't sure, it fails safe and the answer stays
*unclear*. False "no" answers fell to 5, then to 3 with the final prompt.

Then voice notes broke it in a new way. Given a photo **and** a voice note
together, the model stopped looking at the photo. It also quoted one sentence,
*"a long ridge of loose rock between the lake and the glacier"*, as evidence for
six unrelated answers, including "no fresh rockfall". So now:

- photo and voice are asked about **separately**, then merged;
- when they **disagree**, the log shows both and marks the item *unclear*
  instead of picking a side;
- voice evidence must actually appear in the transcript, and must mention
  something the question is about.

Here is that working on a real test stop. The hiker's *"concrete dam"* correctly
answers **moraine dam: no**. Whether the dam is in view ("…behind me") is shown
as a disagreement, not resolved:

![A stop card: the hiker's words answer the moraine-dam question; photo and voice disagree about whether the dam is in view](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/02-evidence.png)

None of these rules needed a bigger model. They are a few dozen lines of plain
Python, and each one exists because a measurement showed the failure it
prevents. Every downgrade is kept, with its reason, so you can see what the
model said as well as what the log kept:

![Downgraded answers listed with their reasons](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/04-downgrades.png)

## What real photos taught me

Labelled photos only go so far, so I also built two realistic test days in
Gilgit-Baltistan (Hunza and Skardu) from geotagged Wikimedia photos. They
include glaciers with no lake in frame, villages with no water at all, a dammed
reservoir and one heavily edited winter photo. They found things my tests
hadn't:

- **A confident hallucination.** On the heavily edited, HDR-style winter photo
  of Borith Lake, Gemma "saw" a moraine dam, low freeboard and the outlet, each
  with plausible evidence. No rule can catch that: the evidence reads fine and
  the model says the dam is in view. Plain phone photos are what this is built
  for, and the README says so.
- **A rule that had never worked.** While editing, I let a script write the
  regex `\b` in the "I can't see it" rule as a literal backspace character. The
  rule matched nothing, and its tests still passed because a *different* rule
  downgraded the same answers. The tests for that rule now check the *reason*
  for the downgrade, and I confirmed they fail on the old code.
- **A bug I found by watching my own demo video.** At a stop with a fort and no
  lake, the photo pass claimed the dam was in view and the voice pass
  disagreed. The merge correctly marked "dam in view" as a disagreement, but the
  photo's *"steep dam face: yes"* had already passed its own check. The in-view
  rule now runs again after merging.
- **Place names get misheard.** "Attabad" came back as "A bad lake", and
  "Satpara" as "Sapporo". The observations survive; the names don't.

## Why open matters here

**There is no signal where the lakes are.** Above the tree line in the
Himalaya and the Karakoram, mobile data can be gone for days. A cloud API is
useless exactly where this tool is needed. Lake Lookout runs entirely on the
laptop and enforces it: while it processes a day, **every network connection
except the one to the local model raises an error**. Offline isn't a setting
you can forget to turn on.

**The data shouldn't leave.** A field log is a list of exact coordinates of
lakes, trails and villages, plus a person's voice. With open weights running
locally, none of it goes to a server I don't control. The page it produces has
no scripts, no web fonts and no map tiles, and it opens with the network off.

**I could measure, swap and iterate for free.** Five prompt versions × 11
photos × several models is a lot of calls. Locally, each one cost nothing and
took about two seconds. That is what made the measurement loop above possible.
I ran the same photos through three local models:

| model | accuracy | false "yes" | false "no" | per photo (RTX 4090) |
|---|---|---|---|---|
| gemma4:e4b | 88% | 0 | 3 | 2.4 s |
| gemma4:e2b | 85% | 1 | 7 | 1.6 s |
| gemma3:4b (v3 prompt) | 65% | 7 | 4 | not comparable* |

E4B is the default because it made the fewest false "no" answers in every run.
**No GPU? `--cpu` switches to E2B**, which took about 20 s per photo on a desktop
CPU (Intel i7-12700F), roughly three minutes for an eight-stop day. A laptop
chip will be slower, but it's still an evening task, not a cloud bill.

\*Another program held most of the GPU's memory during that run.

**One small open model does the whole job.** Gemma 4's E2B and E4B take audio
*and* images. The same local model transcribes the voice note, reads the photo,
and returns JSON constrained to a schema. There is no separate speech model to
install and no second runtime: one `ollama pull` and you have the whole
pipeline.

## Best Use of Gemma

Gemma 4 is the core of Lake Lookout, not an add-on:

- **Speech:** Gemma 4 transcribes each voice note directly from audio.
- **Vision:** Gemma 4 reads each photo against the checklist.
- **Structured output:** answers come back as schema-constrained JSON with
  evidence and source for every item, and field order was used deliberately to
  make the model ground itself before answering.
- **On-device class:** E4B on a GPU and E2B on a CPU-only laptop, both fully
  offline through Ollama.
- **Measured, not assumed:** a labelled evaluation, a three-model comparison,
  and the honest failure cases above.

## How it's built

```
phone photos (EXIF time + GPS) ─┐
phone voice notes (m4a/mp3/…) ──┼─► group into stops (time + distance, UTC-safe)
                                │
                                ▼
          ┌─────────── offline guard: only 127.0.0.1 ───────────┐
          │  ffmpeg → 16 kHz WAV ─► Gemma 4: transcript          │
          │  photo ─► Gemma 4: checklist JSON (evidence first)   │
          │  voice ─► Gemma 4: checklist JSON (evidence first)   │
          │  rules: evidence · in-view · transcript · keywords   │
          │  merge photo + voice (disagreement → shown, unclear) │
          └──────────────────────────────────────────────────────┘
                                ▼
          trip.html (self-contained) · field_log.csv · field_log.geojson
```

- **Python** standard library plus Pillow, **ffmpeg** for audio, **Ollama** for
  Gemma 4.
- **The app** (`python -m lookout ui`) is a small local server, listening only
  on your own machine, with a plain HTML/CSS/JS front end and no libraries. It
  has drag-and-drop days, live progress per stop, an offline route map, filters
  and one-click evidence. It works in dark mode and at phone width.
- **Three levels of testing:**
  - **59 unit and API tests.** The API tests run the real server with a
    stand-in model.
  - **A checker** that compares each generated trip page with its CSV.
  - **A browser end-to-end test** that drives headless Chrome through the whole
    app with the real model and makes 25 checks. It creates a day, uploads
    through the file picker and processes it. Then it uses the map, filters,
    evidence and lightbox, checks every photo decodes and that there's no
    sideways scroll on a phone, and expects zero console errors.

![Lake Lookout on a phone](https://raw.githubusercontent.com/[YOUR_GITHUB_USERNAME]/lake-lookout/main/docs/post/05-phone.png)

Try it yourself in a few minutes; the repo includes test days:

```bash
ollama pull gemma4:e4b      # or gemma4:e2b for a laptop without a GPU
git clone https://github.com/[YOUR_GITHUB_USERNAME]/lake-lookout && cd lake-lookout
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
# python -m venv .venv && .venv/bin/pip install -r requirements.txt     # macOS/Linux
python -m lookout ui        # then open the test-hunza day and press Process
```

## Honest limits

- **Small evaluation.** 11 labelled photos. Scores move a few points between
  runs even at temperature 0, so treat small differences as noise.
- **"Is the dam in view?" is the model's weak spot** (24 to 41% across runs).
  The rule fails safe, so a wrong "not in view" costs answers rather than
  producing false ones.
- **Edited photos can fool it,** as the winter Borith photo showed.
- **Voice in other languages:** the transcription prompt asks for the original
  language plus an English line, but I have only tested English so far.
  [IF YOU RECORDED IN URDU OR NEPALI, SAY WHAT HAPPENED HERE.]
- **It is not a hazard assessment, and it won't become one by adding a score.**

## What's next

- Voice notes in **Urdu and Nepali** from the guides and porters who walk past
  these lakes most often, with English in the log.
- A way to hand a season of logs to the people who study these lakes, in the
  format they actually want. I'd rather ask them than guess.
- Running E2B on the phone itself, so the evening step needs no laptop.

## Credits and disclosure

- **Built during the challenge window.** The repository was created and built
  this week; the commit history shows it going from an empty folder to this.
  The satellite project mentioned at the top is earlier, separate work: it's
  the reason this one exists, not part of it.
- **Built with Claude Code** as my coding agent. The `eval/results/` folder is
  the loop we actually worked in: hypothesis, change, measured result.
  [OPTIONAL: link or embed your agent session here.]
- **Narration:** Kokoro-82M (Apache-2.0) through kokoro-onnx, run locally. The
  video is recorded from the real app with Playwright (`tools/record_demo.py`).
- **Photos:** all evaluation and test-day photos are from Wikimedia Commons
  under CC BY / CC BY-SA licences, credited in `eval/photos/ATTRIBUTION.md` and
  in each test day's README.
- **Licence:** MIT.

Thanks for reading. If you live or walk near glacial lakes and want to try it,
I'd love to hear what it gets wrong. [OPTIONAL: YOUR CONTACT OR SOCIAL LINK]
