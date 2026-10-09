# Before publishing the DEV post

`lake-lookout-dev-post.md` is ready to paste into DEV's editor once every
`[SQUARE BRACKET]` line is replaced: 11 image placeholders (table below) and the
optional agent-session line. The post follows DEV's official submission template
(What I Built, Demo, Code, How I Built It, Why Does Open Innovation Matter?,
My Agent Session, Prize Categories). Search the file for a line starting with `[`.

1. ~~GitHub username~~ done: the repo is https://github.com/hassan-2050/lake-lookout and every
   image and demo link in the post points at it.
2. ~~Video~~ done: https://youtu.be/axjGCMU2-k4 (2 min, with the 'how it was measured'
   segment and uploaded English captions); embedded in the post and linked from the README.
3. ~~Taking it outside~~ written as an honest **dry run** on the Hunza test day.
   After a real walk, replace it with what actually happened (and a screenshot).
4. ~~Label review~~ done as a second pass by the coding agent (four labels changed to
   skip); the post says so. A person can still review: `python tools/make_label_review.py`
   then open `eval/label-review.html`.
5. ~~Language note and optional links~~ removed (English only so far).
6. ~~Live demo~~ on: https://hassan-2050.github.io/lake-lookout/
7. **Agent session (optional).** Under *My Agent Session* there is a line
   `[OPTIONAL AGENT SESSION: ...]`. Save the session with DevRelay and paste its
   `agent_session` embed there (see the challenge page), or delete the line.
8. Set `published: true` (or use DEV's publish button), keep the tags
   `devchallenge, hf26challenge`, and select the **Best Use of Gemma** prize
   category if the template asks.

## Images: replace each bracket with an upload

Every image in the post is a placeholder line like
`[SCREENSHOT 1: upload docs/post/01-app.png, alt text: "..."]`.
In DEV's editor, put the cursor on that line, click the **image** button in the
toolbar, upload the named file from `G:\lake-lookout\`, then delete the bracket
line and paste the alt text into the brackets of the `![](...)` DEV inserts.

| placeholder | file to upload | where it is |
|---|---|---|
| SCREENSHOT 1 | `docs/post/01-app.png` | top, under the TL;DR |
| GIF 1 | `docs/post/clips/1-process.gif` | What I Built › How a day works |
| GIF 2 | `docs/post/clips/2-evidence.gif` | Demo, under the video |
| SCREENSHOT 2 | `docs/post/10-live-demo.png` | Demo, under the live-demo link |
| SCREENSHOT 3 | `docs/post/07-trip-page.png` | What I Built › Taking it outside |
| SCREENSHOT 4 | `docs/post/09-iterations.png` | How I Built It › making a small model unable to overclaim |
| SCREENSHOT 5 | `docs/post/02-evidence.png` | How I Built It, the Satpara evidence card |
| GIF 3 | `docs/post/clips/3-disagree.gif` | right after Screenshot 5 |
| SCREENSHOT 6 | `docs/post/04-downgrades.png` | How I Built It, downgraded answers |
| SCREENSHOT 7 | `docs/post/06-dark.png` | How I Built It › Open-source AI at the core |
| GIF 4 | `docs/post/clips/5-phone.gif` | How I Built It, right after Screenshot 7 |

**Cover image:** the post's front matter already points `cover_image` at
`docs/post/cover.png` on GitHub. If you'd rather upload it, use DEV's
"Add a cover image" button with `docs/post/cover.png` and delete the
`cover_image:` line.

Spare material: `docs/post/clips/4-live-demo.gif` (the live site),
`docs/post/03-map.png` (map with photo preview), `docs/post/05-phone.png`,
`docs/post/08-home.png`, and every clip as `.mp4` in `docs/post/clips/`.

Deadline: **11 October 2026, 11:59 PM PDT** (12 October, 11:59 AM in Pakistan).
