# Launch checklist — the steps only you can do

Work top to bottom; items marked **⏸ report back** unblock work on my side.
Business entity everywhere: **Lamaute Labs LLC**. Pricing: **$8/mo · $79/yr prepaid**.

---

## 1 · Download the PyLocket-ready Designer artifacts (~now)

CI now produces **raw PyInstaller zips** (what PyLocket accepts) alongside the
installers.

1. Go to <https://github.com/klamaute/Elysium/actions/runs/28615834679>
   (workflow: *Release Designer*).
2. Wait for all four jobs to go green, then scroll to **Artifacts** and download:
   - `Elysium-Designer-macOS-arm64-pylocket.zip` (PyInstaller **onedir**, zipped)
   - `Elysium-Designer-macOS-x86_64-pylocket.zip` (onedir, zipped)
   - `Elysium-Designer-Windows-x64-pylocket.zip` (PyInstaller **onefile** .exe, zipped)
   - `Elysium-Designer-Linux-x86_64-pylocket.zip` (onedir, zipped)
3. **Upload these zips to PyLocket** — *not* the .dmg / Setup.exe / .AppImage
   (those are installers; PyLocket rejects them by design).

> Note: GitHub wraps each artifact in an extra download zip. If PyLocket
> complains about the file you uploaded, unzip the *download* once and upload
> the inner `…-pylocket.zip`.

## 2 · PyLocket — product, pricing, licensing  ⏸ report back

1. <https://pylocket.com> → create the account / verify identity, set the
   business profile to **Lamaute Labs LLC**.
2. Create the app: name **Elysium Designer**, version **1.1.1**.
3. Upload the four platform zips from step 1 (macOS arm64 / macOS Intel /
   Windows x64 / Linux x86_64).
4. Configure licensing: **30-day free trial**, then subscription —
   **$8/month** and **$79/year (prepaid annual)**. Wire the payment provider in
   PyLocket's fulfillment settings.
5. Follow their multi-OS publishing guide if anything looks off:
   <https://docs.pylocket.com/part-1-tutorials/multi-os-publishing/>
6. **⏸ Send me:** the per-OS **trial download URLs** and the **checkout/buy
   URL**. I'll replace the TODO placeholders in
   `website/src/data/downloads.ts` and rebuild the site.

## 3 · Cloudflare — account + zone (DNS hosting; registration stays at Dynadot)

1. <https://dash.cloudflare.com/sign-up> → create the account (Free plan).
2. **Add a domain** → `elysiumui.com` → choose **Free** → Cloudflare shows
   **two nameservers** (e.g. `xxx.ns.cloudflare.com`, `yyy.ns.cloudflare.com`).
   Keep this tab open.
3. Let Cloudflare import any existing DNS records (fine either way).

## 4 · Dynadot — point nameservers at Cloudflare

1. <https://www.dynadot.com> → sign in → **My Domains** → `elysiumui.com` →
   **Manage** → **Name Servers** (a.k.a. DNS settings).
2. Choose the option to use **custom/your own name servers** and enter the two
   Cloudflare nameservers from step 3. Save.
3. Propagation: usually minutes-to-hours (up to 24 h). Cloudflare emails you
   when the zone goes **Active**. Nothing else changes at Dynadot — it remains
   your registrar; renewals stay there.

## 5 · Cloudflare Pages — the website  ⏸ report back

Once the zone is Active (site works before that via `*.pages.dev` too):

1. Dash → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** →
   authorize the Cloudflare GitHub app for **klamaute/Elysium** (private repos
   are supported).
2. Build settings — set exactly:
   - **Root directory:** `website`
   - **Build command:** `npm ci && npm run build`
   - **Build output directory:** `dist`
3. Deploy → you get `https://<project>.pages.dev`. Check it renders.
4. Project → **Custom domains** → add `elysiumui.com`, then add
   `www.elysiumui.com` (Cloudflare creates the DNS records automatically since
   the zone is on Cloudflare; SSL is automatic).
5. Project → **Settings → Web Analytics** → enable (cookie-less, free).
6. **⏸ Tell me when apex + www are serving** — then I'll do the docs migration
   (mkdocs `site_url` + CNAME files for `docs.` / `designer.elysiumui.com`) and
   walk you through the two GitHub Pages custom-domain fields.

## 6 · Purelymail — email on elysiumui.com

1. <https://purelymail.com> → create the account (flat ~$10/yr).
2. **Add domain** → `elysiumui.com`. Purelymail shows DNS records:
   ownership TXT, **MX**, SPF TXT, and **DKIM** records.
3. Add each in **Cloudflare** (dash → `elysiumui.com` → **DNS → Records**):
   copy them exactly; MX and DKIM/CNAME records must be **DNS only** (grey
   cloud, not proxied). TXT records are DNS-only by nature.
4. Back in Purelymail, hit **verify**; then create users/routing:
   - `support@elysiumui.com` (used on the site + PyLocket fulfillment reply-to)
   - `sales@`, `hello@` → route/alias to the same inbox if you like.
5. Send yourself a test in + out.

## 7 · GitHub — secret for the private Designer repo's CI

The Designer now builds from **klamaute/elysium-designer** (private) and needs
read access to the framework repo until `elysium-ui` is on PyPI:

1. <https://github.com/settings/personal-access-tokens/new> → **Fine-grained
   token**: Resource owner *klamaute*; **Only select repositories** →
   `klamaute/Elysium`; Permissions → **Contents: Read-only**. 1-year expiry.
2. <https://github.com/klamaute/elysium-designer/settings/secrets/actions> →
   **New repository secret** → name `FRAMEWORK_REPO_TOKEN`, paste the token.
3. Optional check: repo → Actions → run **Release Designer** → artifacts should
   build there exactly like they did in the monorepo.

## 8 · Report back → what I finish from here

- PyLocket URLs → wired into the site, rebuild, push.
- Apex/www live → docs migration (site_url + CNAME + the GitHub Pages
  custom-domain settings for `docs.` and `designer.`).
- Later, on your word: make this repo public (the Designer source is already
  out) and publish `elysium-ui` to PyPI.
