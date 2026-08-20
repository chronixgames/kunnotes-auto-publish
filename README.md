# kunnotes-auto-publish

Tistory finance/economy auto-publishing scaffold.

## Flow
- Fetch fresh finance/economy RSS items
- Select 3 non-duplicate topics
- Generate Korean SEO articles with OpenAI
- Pick deterministic random KST slots in morning/lunch/evening windows
- Publish through a browser session when `TISTORY_STORAGE_STATE` is configured

## Required GitHub Actions secrets
- `OPENAI_API_KEY`
- `TISTORY_STORAGE_STATE` — base64-encoded Playwright storage-state JSON for an already authenticated Kakao/Tistory browser session
- `TISTORY_BLOG_NAME` — blog name, e.g. `kunnotes`

The browser publisher intentionally uses an authenticated session rather than storing a password. If the Tistory session expires, refresh the storage-state secret.

## Safety
The workflow defaults to `DRY_RUN=true`. Change the workflow environment to `false` only after verifying a generated draft in the logs/artifact.

GitHub Actions cron is best-effort; it can start late. The workflow checks the intended KST slot before publishing.