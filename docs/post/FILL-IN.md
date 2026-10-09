# Before publishing the DEV post

`lake-lookout-dev-post.md` is ready to paste into DEV's editor once every
`[SQUARE BRACKET]` is replaced. Search the file for `[` to find them all.

1. **`[YOUR_GITHUB_USERNAME]`** (appears many times): push this repo to GitHub
   as a **public** repo named `lake-lookout`, then find-and-replace your
   username. Every image is loaded from `docs/post/` in that repo, so check
   that one image URL opens in a browser before you publish.
2. **`[YOUR_YOUTUBE_OR_LOOM_URL]`**: upload `docs/post/lake-lookout-demo.mp4`
   (98 s, 1280×720, narrated) to YouTube (unlisted is fine) or Loom, and paste the link.
   DEV embeds it with `{% embed ... %}`.
3. **Taking it outside**: write it after your outing, using the structure
   inside the brackets. Use only what really happened. Add a screenshot of your
   own trip page to `docs/post/` and link it.
4. **`[LABEL REVIEW ...]`**: review `eval/labels.json` (11 photos), then keep
   the sentence that is true.
5. **`[IF YOU RECORDED IN URDU OR NEPALI ...]`**: say what happened, or delete
   the bracket if you only used English.
6. **Optional**: agent session link or embed, and your contact or social link.
   Delete these brackets if you don't use them.
7. **Turn on the live demo**: in the GitHub repo, go to Settings → Pages →
   Deploy from a branch → `main`, folder `/docs` → Save. After a minute or two,
   check that `https://[YOUR_GITHUB_USERNAME].github.io/lake-lookout/` opens the
   demo. (Optional: re-export with your repo link so the demo's home page links
   to the code: `python -m lookout export --out docs/demo --featured test-hunza
   --repo https://github.com/[YOUR_GITHUB_USERNAME]/lake-lookout`, then commit
   and push.)
8. Set `published: true` (or use DEV's publish button), keep the tags
   `devchallenge, hf26challenge`, and select the **Best Use of Gemma** prize
   category if the template asks.

Deadline: **11 October 2026, 11:59 PM PDT** (12 October, 11:59 AM in Pakistan).
