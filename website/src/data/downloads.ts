/**
 * Single source of truth for every download / install / external link on the
 * site. Update HERE, nowhere else.
 *
 * Two tracks:
 *  A — Framework: free + open source (Apache-2.0). PyPI + public GitHub repo.
 *  B — Designer:  commercial, closed source. Free trial + paid license served
 *      by PyLocket (protected builds, license keys, checkout).
 */

/** Framework — Track A ---------------------------------------------------- */
export const framework = {
  /** NOTE: `elysium` is taken on PyPI (dead project) — we ship as elysium-ui. */
  pipPackage: 'elysium-ui',
  pipCommand: 'pip install elysium-ui',
  importName: 'elysium',
  /** Static fallback shown until the live-version fetch resolves. */
  version: '1.1.1',
  license: 'Apache-2.0',
  pypiUrl: 'https://pypi.org/project/elysium-ui/',
  /** The public framework repo (post-split). TODO: flip when the split lands. */
  repoUrl: 'https://github.com/elysiumui/elysium',
  releasesApi: 'https://api.github.com/repos/elysiumui/elysium/releases/latest',
} as const;

/** Designer — Track B ----------------------------------------------------- */
export type OsKey = 'mac-arm' | 'mac-intel' | 'windows' | 'linux';

export interface DesignerBuild {
  os: OsKey;
  label: string;
  arch: string;
  icon: 'apple' | 'windows' | 'linux';
}

export const designer = {
  name: 'Elysium Designer',
  version: '1.0.0',
  trialDays: 14,
  priceMonthly: 8,
  priceYearly: 79,
  /** One PyLocket trial link for every OS — the user enters their email and
   *  picks the platform there. */
  trialUrl: 'https://get.pylocket.com/t/AwTOf_-qftFk8P2qdhd3quTdomjcHVgnkDNPphAqsKc',
  /** Stripe account still under review — no checkout links yet. When they
   *  arrive, set buyUrl and the "coming soon" state disappears. */
  buyUrl: '',
  eulaPath: '/eula',
  /** Platform availability (display only — the trial link covers them all). */
  builds: [
    { os: 'mac-arm', label: 'macOS', arch: 'Apple Silicon', icon: 'apple' },
    { os: 'mac-intel', label: 'macOS', arch: 'Intel', icon: 'apple' },
    { os: 'windows', label: 'Windows', arch: 'x64', icon: 'windows' },
    { os: 'linux', label: 'Linux', arch: 'x86_64 AppImage', icon: 'linux' },
  ] satisfies DesignerBuild[],
} as const;

/** External destinations -------------------------------------------------- */
export const company = {
  legalName: 'Lamaute Labs LLC',
} as const;

export const links = {
  docs: 'https://docs.elysiumui.com',
  designerDocs: 'https://designer.elysiumui.com',
  tutorial: 'https://docs.elysiumui.com/tutorials/shopify-style-desktop-app/',
  gallery: 'https://docs.elysiumui.com/resources/component-gallery/',
  github: 'https://github.com/elysiumui/elysium',
  supportEmail: 'support@elysiumui.com',
} as const;
