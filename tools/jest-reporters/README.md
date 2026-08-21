# jest-reporters helper

One-time setup (not run automatically — needs network access):

```bash
cd tools/jest-reporters
npm install
```

This installs `jest-junit` here so it can be referenced by absolute path
(`tools/jest-reporters/node_modules/jest-junit/index.js`) when running
ts-pattern's own Jest suite — without ever touching ts-pattern's own
`package.json` or lockfile.
