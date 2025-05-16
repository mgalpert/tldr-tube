# TLDR Tube - Auto cut any youtube video to the most important parts

### Web (NextJS) Code

To run the TLDR Tube web code, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

You will need to add your your Sieve API key to `.env.local`

```
SIEVE_KEY=
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Backend Sieve Functions

All of the segment download and processing happens in a Sieve funciton in the `sieve-functions/`
directory. The entry point for the function is in `create_video.py`.

You will need to add your `OPENAI_KEY=` into a `.env` file in the `sieve-functions/` directory.

Additionally you will also need to ensure that you download the the requirements by running:

```bash
pip install -r requirements.txt
```

#### You can then deploy your sieve function with :

Login with your sieve key:

```bash
sieve login
```

Deploy your sieve function:

```bash
sieve deploy create_video.py
```
