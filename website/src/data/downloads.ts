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
  repoUrl: 'https://github.com/klamaute/Elysium',
  releasesApi: 'https://api.github.com/repos/klamaute/Elysium/releases/latest',
} as const;

/** Designer — Track B ----------------------------------------------------- */
export type OsKey = 'mac-arm' | 'mac-intel' | 'windows' | 'linux';

export interface DesignerBuild {
  os: OsKey;
  label: string;
  arch: string;
  /** PyLocket-hosted trial installer URL. TODO(PyLocket): real per-OS URLs. */
  trialUrl: string;
  icon: 'apple' | 'windows' | 'linux';
}

const PYLOCKET_BASE = 'https://pylocket.com/d/elysium-designer'; // TODO(PyLocket): confirm

export const designer = {
  name: 'Elysium Designer',
  version: '1.1.1',
  trialDays: 30,
  priceMonthly: 8,
  priceYearly: 79,
  /** TODO(PyLocket): real checkout URL once the product is registered. */
  buyUrl: 'https://pylocket.com/buy/elysium-designer',
  eulaPath: '/eula',
  builds: [
    {
      os: 'mac-arm',
      label: 'macOS',
      arch: 'Apple Silicon',
      trialUrl: `${PYLOCKET_BASE}/macos-arm64`,
      icon: 'apple',
    },
    {
      os: 'mac-intel',
      label: 'macOS',
      arch: 'Intel',
      trialUrl: `${PYLOCKET_BASE}/macos-x86_64`,
      icon: 'apple',
    },
    {
      os: 'windows',
      label: 'Windows',
      arch: 'x64',
      trialUrl: `${PYLOCKET_BASE}/windows-x64`,
      icon: 'windows',
    },
    {
      os: 'linux',
      label: 'Linux',
      arch: 'x86_64 AppImage',
      trialUrl: `${PYLOCKET_BASE}/linux-x86_64`,
      icon: 'linux',
    },
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
  github: 'https://github.com/klamaute/Elysium',
  supportEmail: 'support@elysiumui.com',
} as const;
