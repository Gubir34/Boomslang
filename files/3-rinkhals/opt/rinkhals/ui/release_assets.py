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


def update_asset_names(model_code):
    groups = UPDATE_ASSET_GROUPS.get((model_code or '').strip().upper(), [])
    return [f'update-{group}.swu' for group in groups]


def find_update_asset(assets, model_code):
    """Return the release asset (a GitHub API dict) to install, or None."""
    by_name = {}
    for asset in assets or []:
        name = (asset.get('name') or '').lower()
        by_name.setdefault(name, asset)
    for name in update_asset_names(model_code):
        if name in by_name:
            return by_name[name]
    return None

