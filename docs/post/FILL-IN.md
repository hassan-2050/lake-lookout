# Before publishing the DEV post

`lake-lookout-dev-post.md` is ready to paste into DEV's editor once every
`[SQUARE BRACKET]` is replaced: 11 image placeholders (table below) and the label sentence. Search the file for `[` to find them all.

1. ~~GitHub username~~ done: the repo is https://github.com/hassan-2050/lake-lookout and every
   image and demo link in the post points at it.
2. ~~Video~~ done: https://youtu.be/1rj782juY7c is embedded in the post. If you haven't yet, add
   the captions in YouTube Studio: Subtitles → Add language (English) →
   Upload file → **With timing** → `docs/post/lake-lookout-demo.srt`.
3. ~~Taking it outside~~ written as an honest **dry run** on the Hunza test day.
   After a real walk, replace it with what actually happened (and a screenshot).
4. **`[LABEL REVIEW ...]`**: review the labels on the review page
   (https://claude.ai/artifact/1k3NpxB3uWfnFArZQENoiG), then tell Claude; it re-scores
   and replaces this sentence. This is the last bracket left.
5. ~~Language note and optional links~~ removed (English only so far).
6. ~~Live demo~~ on: https://hassan-2050.github.io/lake-lookout/
7. Set `published: true` (or use DEV's publish button), keep the tags
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
| SCREENSHOT 1 | `docs/post/01-app.png` | under the TL;DR |
| GIF 1 | `docs/post/clips/1-process.gif` | end of "What I built" list |
| GIF 2 | `docs/post/clips/2-evidence.gif` | Demo, under the video |
| SCREENSHOT 2 | `docs/post/10-live-demo.png` | Demo, under the live-demo link |
| SCREENSHOT 3 | `docs/post/07-trip-page.png` | Taking it outside |
| SCREENSHOT 4 | `docs/post/09-iterations.png` | the measured-versions chart |
| SCREENSHOT 5 | `docs/post/02-evidence.png` | the Satpara evidence card |
| GIF 3 | `docs/post/clips/3-disagree.gif` | right after Screenshot 5 |
| SCREENSHOT 6 | `docs/post/04-downgrades.png` | downgraded answers |
| SCREENSHOT 7 | `docs/post/06-dark.png` | How it's built (dark mode) |
| GIF 4 | `docs/post/clips/5-phone.gif` | How it's built (phone) |

**Cover image:** the post's front matter already points `cover_image` at
`docs/post/cover.png` on GitHub. If you'd rather upload it, use DEV's
"Add a cover image" button with `docs/post/cover.png` and delete the
`cover_image:` line.

Spare material: `docs/post/clips/4-live-demo.gif` (the live site),
`docs/post/03-map.png` (map with photo preview), `docs/post/05-phone.png`,
`docs/post/08-home.png`, and every clip as `.mp4` in `docs/post/clips/`.

Deadline: **11 October 2026, 11:59 PM PDT** (12 October, 11:59 AM in Pakistan).
