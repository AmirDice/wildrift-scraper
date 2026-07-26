This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Environment

Everything below is optional: without it the site still builds and runs, it just
degrades the feature that depends on it.

| Variable | Used for | Without it |
| --- | --- | --- |
| `NEXT_PUBLIC_BUILD_TOOLS` | `1` forces the Build Optimizer and Counter Builder on, `0` off. Unset means on in dev, off in production. | Tools hidden in production |
| `DEEPSEEK_API_KEY` | The build advisor (`web/build_advisor.py`) spawned by `/api/build`. | Generation returns an error |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google Identity Services client id, used by the sign-in button. | Sign-in UI is hidden entirely |
| `AUTH_SECRET` | HMAC key for our session cookie. Any long random string. | Sign-in UI is hidden entirely |
| `KV_REST_API_URL` + `KV_REST_API_TOKEN` | Everything persistent: daily build quotas, "builds generated", likes, feedback, **build albums and duo blends**. `UPSTASH_REDIS_REST_*` works too. | Counters and albums live in process memory: they reset on redeploy and are not shared between instances, so albums effectively do not persist |
| `ADMIN_TOKEN` | Unlocks `/api/admin/usage?token=…`, the internal read-out of feature usage and build feedback. | That route returns 404 |

Sign-in requires **both** `NEXT_PUBLIC_GOOGLE_CLIENT_ID` and `AUTH_SECRET`; the
UI checks for both and hides itself if either is missing, so a half-configured
deployment never shows a button that cannot work.

Generate a session secret with:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

The Google client id comes from a **Web application** OAuth client in the Google
Cloud console, with the site origin (and `http://localhost:3000` for dev) listed
under "Authorised JavaScript origins".

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
