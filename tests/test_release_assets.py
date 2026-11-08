"""The touch UI must download the update package for this exact printer."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'testsupport.release_assets',
    Path(__file__).resolve().parents[1] / 'files/3-rinkhals/opt/rinkhals/ui/release_assets.py')
release_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_assets)


def assets(*names):
    return [{'name': n, 'browser_download_url': f'https://example.invalid/{n}'} for n in names]


# Listed in the order that broke the old substring match: k3m before k2p-k3,
# ks1m before ks1
ALL = assets('installer-ks1.swu', 'update-k3m.swu', 'update-k2p-k3.swu',
             'update-ks1m.swu', 'update-ks1.swu', 'tools-ks1.zip')


class FindUpdateAssetTests(unittest.TestCase):
    def test_each_model_gets_its_own_package(self):
        expected = {
            'K2P': 'update-k2p-k3.swu', 'K3': 'update-k2p-k3.swu', 'K3V2': 'update-k2p-k3.swu',
            'K3M': 'update-k3m.swu', 'KS1': 'update-ks1.swu', 'KS1M': 'update-ks1m.swu',
        }
        for model, name in expected.items():
            with self.subTest(model=model):
                self.assertEqual(release_assets.find_update_asset(ALL, model)['name'], name)

    def test_s1_max_falls_back_to_the_ks1_package(self):
        self.assertEqual(
            release_assets.find_update_asset(assets('update-ks1.swu'), 'KS1M')['name'], 'update-ks1.swu')

    def test_no_package_and_unknown_model(self):
        self.assertIsNone(release_assets.find_update_asset(assets('installer-ks1.swu'), 'KS1'))
        self.assertIsNone(release_assets.find_update_asset(ALL, 'K4'))
        self.assertIsNone(release_assets.find_update_asset(None, 'KS1'))


if __name__ == '__main__':
    unittest.main()
