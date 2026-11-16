"""Pick the right update package from a GitHub release for this printer.

Releases carry update-k2p-k3.swu, update-k3m.swu, update-ks1.swu and
update-ks1m.swu. Matching by substring was wrong: "k3" is in "k3m" and
"ks1" in "ks1m", so the choice depended on the order GitHub listed them.
Packages are matched by exact name instead, in the same groups as the web
portal (65-rinkhals-web/catalog.go modelToAssetGroup).
"""

# Most specific first. KS1 and KS1M packages are identical (same password and
# content), so an S1 Max can fall back to update-ks1.swu on older releases.
UPDATE_ASSET_GROUPS = {
    'K2P': ['k2p-k3'],
    'K3': ['k2p-k3'],
    'K3V2': ['k2p-k3'],
    'K3M': ['k3m'],
    'KS1': ['ks1'],
    'KS1M': ['ks1m', 'ks1'],
}


def update_asset_names(model_code, compressed=False):
    """Package names to look for, best first.

    Releases carry a standard package (update-ks1.swu, setup.tar.gz inside,
    installable from USB) and a compressed one (update-ks1-compressed.swu,
    setup.tar.xz, smaller, only for the OTA of a running Boomslang, see
    swu_setup.py). compressed=True prefers the compressed one and falls back
    to the standard one, which older releases only have.
    """
    groups = UPDATE_ASSET_GROUPS.get((model_code or '').strip().upper(), [])
    standard = [f'update-{group}.swu' for group in groups]
    if not compressed:
        return standard
    return [f'update-{group}-compressed.swu' for group in groups] + standard


def firmware_listed(release_notes, firmware):
    """Whether a release's notes name this firmware version.

    Rinkhals release notes carry a "Supported printers" table with the
    tested firmware versions. 2.7.3 must not match inside 2.7.3.7.
    """
    import re
    if not release_notes or not firmware:
        return False
    return re.search(rf'(?<![\d.]){re.escape(firmware)}(?![\d.]*\d)', release_notes) is not None


def switch_warning_text(version, release_notes, firmware):
    """The warning kept on screen in the last step of "Switch to Rinkhals"."""
    if firmware_listed(release_notes, firmware):
        return (f'Rinkhals {version} lists firmware {firmware} as supported. '
                'Boomslang will be replaced. To come back, install Boomslang from a USB drive.')
    return (f'Firmware {firmware or "?"} is NOT listed as supported by Rinkhals {version}. '
            'Rinkhals will probably not start and the printer will run the stock software only. '
            'To come back, install Boomslang from a USB drive.')


def find_update_asset(assets, model_code, compressed=False):
    """Return the release asset (a GitHub API dict) to install, or None."""
    by_name = {}
    for asset in assets or []:
        name = (asset.get('name') or '').lower()
        by_name.setdefault(name, asset)
    for name in update_asset_names(model_code, compressed):
        if name in by_name:
            return by_name[name]
    return None


# Release names: {YY}{M} {N} {Channel}, for example "2611 3 Alpha": year 2026,
# November (months 1 to 12, not zero padded), the 3rd release of that month
# (0 to 999, counted across all channels), Alpha channel. Git tags and the
# version folders on the printer can't hold spaces, so the tag is the same
# thing written 2611-3-alpha; display_version() turns it back into the name.
# Keep in step with firmware.go in the web portal and auto-release.yml.
CHANNELS = ('alpha', 'beta', 'release-preview', 'release')   # least to most stable
CHANNEL_NAMES = {'alpha': 'Alpha', 'beta': 'Beta', 'release-preview': 'Release Preview', 'release': 'Release'}
_TAG = r'^(\d{2})(1[0-2]|[1-9])-(\d{1,3})-(alpha|beta|release-preview|release)$'
_LEGACY_TAG = r'^(\d{8})_(\d+)'   # 20261108_04, 20261108_04_test (before the new names)


def parse_release_tag(tag):
    """{'year', 'month', 'number', 'channel'} from 2611-3-alpha, else None."""
    import re
    m = re.match(_TAG, (tag or '').strip().lower())
    if not m:
        return None
    return {'year': int(m.group(1)), 'month': int(m.group(2)),
            'number': int(m.group(3)), 'channel': m.group(4)}


def display_version(tag):
    """2611-3-alpha -> '2611 3 Alpha'. Anything else is shown as it is."""
    parsed = parse_release_tag(tag)
    if not parsed:
        return tag or ''
    return f"{parsed['year']:02d}{parsed['month']} {parsed['number']} {CHANNEL_NAMES[parsed['channel']]}"


def release_tag_key(tag):
    """A sortable key for a release tag, else None.

    Every named release (2611-3-alpha) sorts after every dated one
    (20261108_04), which is how the names replaced the dates.
    """
    import re
    parsed = parse_release_tag(tag)
    if parsed:
        return (1, parsed['year'], parsed['month'], parsed['number'], CHANNELS.index(parsed['channel']))
    m = re.match(_LEGACY_TAG, tag or '')
    return (0, int(m.group(1)), int(m.group(2)), 0, 0) if m else None


def is_newer_release(latest, current):
    """True only when latest is a strictly later release than current.

    A version that is not a release tag (a dev build, a git commit) never
    gets an update offered, so nobody is downgraded by a highlighted Update
    button.
    """
    a, b = release_tag_key(latest), release_tag_key(current)
    return bool(a and b and a > b)
