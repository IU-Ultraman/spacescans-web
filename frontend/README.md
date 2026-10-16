# SPACESCANS web frontend

Next.js 14 (App Router). The API base URL is inlined at build time from
`NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Checks

```bash
npm ci
npm run lint
npx tsc --noEmit
npm run build
npm run check:lib   # tsc-emits src/lib/{variable-grouping,datasets,output-level,api}.ts to
                    # .next-check (CommonJS) and runs scripts/check-variable-grouping.mjs plus
                    # the node tests in scripts/*.test.mjs (API client against a mocked fetch/XHR)
```

To work against a backend on another port, start the dev server with that URL,
e.g. `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001 npx next dev -p 3001`.

---

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
