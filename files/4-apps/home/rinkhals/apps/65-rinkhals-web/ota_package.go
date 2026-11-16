package main

import (
	"os"
	"strings"
)

// Releases carry two packages per printer:
//
//	update-ks1.swu             standard: setup.tar.gz inside, installs from USB too
//	update-ks1-compressed.swu  compressed: setup.tar.xz, a smaller download
//
// The OTA (Install button and automatic updates) downloads the compressed one
// unless this app's "ota_package" property is "standard". It is unpacked by
// the touch UI's swu_setup.py, so it is only chosen when the running
// Boomslang has that file.

const otaPackageProperty = "ota_package"

// Replaced in tests.
var swuSetupScript = rinkhalsCurrent + "/opt/rinkhals/ui/swu_setup.py"

func otaPackageCompressed() bool {
	if strings.EqualFold(strings.TrimSpace(readUserConfig(autoUpdateAppID)[otaPackageProperty]), "standard") {
		return false
	}
	_, err := os.Stat(swuSetupScript)
	return err == nil
}
