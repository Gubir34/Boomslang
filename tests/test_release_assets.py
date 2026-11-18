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


class IsNewerReleaseTests(unittest.TestCase):
    def test_strictly_newer_only(self):
        newer = release_assets.is_newer_release
        self.assertTrue(newer('20261109_01', '20261108_04_test'))
        self.assertTrue(newer('20261108_02', '20261108_01'))     # two releases on one day
        self.assertFalse(newer('20261108_01', '20261108_01'))
        self.assertFalse(newer('20261101_01', '20261108_04_test'))  # no downgrade offered
        self.assertFalse(newer('20261108_01', '20261108_01_test'))  # same release, other channel

    def test_unparseable_versions_never_offer_an_update(self):
        newer = release_assets.is_newer_release
        for current in ('dev', 'a1b2c3d', '', None):
            self.assertFalse(newer('20261108_01', current))
        self.assertFalse(newer(None, '20261108_01'))

    def test_named_releases(self):
        newer = release_assets.is_newer_release
        self.assertTrue(newer('2611-4-beta', '2611-3-alpha'))
        self.assertTrue(newer('2612-1-alpha', '2611-999-release'))      # a new month starts again at 1
        self.assertTrue(newer('271-1-alpha', '2612-40-release'))        # January of the next year
        self.assertTrue(newer('2610-1-alpha', '269-5-release'))         # October after September
        self.assertTrue(newer('2611-3-release', '2611-3-alpha'))        # same number, more stable channel
        self.assertFalse(newer('2611-3-alpha', '2611-3-alpha'))
        self.assertFalse(newer('2611-2-release', '2611-3-alpha'))       # no downgrade
        self.assertFalse(newer('2611-1000-alpha', '2611-3-alpha'))      # not a valid name
        self.assertFalse(newer('2613-1-alpha', '2611-3-alpha'))         # no 13th month

    def test_named_releases_replace_dated_ones(self):
        newer = release_assets.is_newer_release
        self.assertTrue(newer('2611-1-alpha', '20261116_09_test'))
        self.assertFalse(newer('20991231_01', '2611-1-alpha'))

    def test_compressed_packages_are_preferred_when_asked(self):
        assets = [{'name': n} for n in ('update-ks1.swu', 'update-ks1-compressed.swu', 'update-k2p-k3.swu',
                                        'update-k2p-k3-compressed.swu', 'update-ks1m.swu')]
        find = release_assets.find_update_asset
        self.assertEqual(find(assets, 'KS1', compressed=True)['name'], 'update-ks1-compressed.swu')
        self.assertEqual(find(assets, 'KS1')['name'], 'update-ks1.swu')       # standard by default
        self.assertEqual(find(assets, 'K3V2', compressed=True)['name'], 'update-k2p-k3-compressed.swu')
        # S1 Max: the KS1 compressed package (same content) beats a standard one
        self.assertEqual(find(assets, 'KS1M', compressed=True)['name'], 'update-ks1-compressed.swu')
        # older releases only have standard packages
        self.assertEqual(find([{'name': 'update-k3m.swu'}], 'K3M', compressed=True)['name'], 'update-k3m.swu')

    def test_firmware_is_looked_up_in_the_release_notes(self):
        notes = '| Kobra S1 | `2.7.0.9` `2.7.2.7` |\n| Kobra 3 | 2.4.6.7 |'
        listed = release_assets.firmware_listed
        self.assertTrue(listed(notes, '2.7.2.7'))
        self.assertTrue(listed(notes, '2.4.6.7'))
        self.assertFalse(listed(notes, '2.7.3.7'))
        self.assertFalse(listed(notes, '2.7.2'))           # not inside 2.7.2.7
        self.assertFalse(listed('| K3 | 12.7.2.7 |', '2.7.2.7'))
        self.assertFalse(listed(None, '2.7.2.7'))
        self.assertIn('NOT listed', release_assets.switch_warning_text('20261101_01', notes, '2.7.3.7'))
        self.assertIn('as supported', release_assets.switch_warning_text('20261101_01', notes, '2.7.2.7'))

    def test_display_names(self):
        show = release_assets.display_version
        self.assertEqual(show('2611-3-alpha'), '2611 3 Alpha')
        self.assertEqual(show('261-12-release-preview'), '261 12 Release Preview')
        self.assertEqual(show('2611-0-release'), '2611 0 Release')
        self.assertEqual(show('20261108_04_test'), '20261108_04_test')  # older tags as they are
        self.assertEqual(show(None), '')


if __name__ == '__main__':
    unittest.main()


class ChannelTests(unittest.TestCase):
    """The touch UI offers a printer the releases of its installed channel and more stable ones."""

    def test_channel_of_a_version(self):
        self.assertEqual(release_assets.channel_of('2611-3-alpha'), 'alpha')
        self.assertEqual(release_assets.channel_of('2611-3-beta'), 'beta')
        self.assertEqual(release_assets.channel_of('2611-3-release'), 'release')
        self.assertEqual(release_assets.channel_of('20261108_04_test'), 'alpha')
        for other in ('20261108_04', 'dev', '', None):
            self.assertEqual(release_assets.channel_of(other), 'release')

    def test_each_channel_gets_its_own_and_more_stable_releases(self):
        offered = release_assets.offered_in_channel
        for tag in ('2611-6-alpha', '2611-6-beta', '2611-6-release'):
            self.assertTrue(offered(tag, 'alpha'))
        self.assertFalse(offered('2611-6-alpha', 'beta'))
        self.assertTrue(offered('2611-6-beta', 'beta'))
        self.assertTrue(offered('2611-6-release', 'beta'))
        self.assertFalse(offered('2611-6-alpha', 'release'))
        self.assertFalse(offered('2611-6-beta', 'release'))
        self.assertTrue(offered('2611-6-release', 'release'))

    def test_an_unknown_channel_is_treated_as_release(self):
        self.assertFalse(release_assets.offered_in_channel('2611-6-alpha', 'nonsense'))
        self.assertTrue(release_assets.offered_in_channel('2611-6-release', None))
