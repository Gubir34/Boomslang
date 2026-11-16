//go:build linux

package main

import "testing"

// Real `lsblk -J -b` output shapes: an internal NVMe disk, a USB stick with
// one FAT32 partition (mounted), a GPT exFAT stick (not mounted), a stick
// formatted without a partition table, and an older lsblk that prints "1".
const lsblkSample = `{"blockdevices": [
 {"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","rm":false,"hotplug":false,"tran":"nvme","fstype":null,"label":null,"size":1000204886016,"pttype":"gpt","model":"Samsung SSD","mountpoint":null,
  "children":[{"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","rm":false,"hotplug":false,"tran":"nvme","fstype":"vfat","label":null,"size":1073741824,"pttype":"gpt","model":null,"mountpoint":"/boot"}]},
 {"name":"sda","path":"/dev/sda","type":"disk","rm":true,"hotplug":true,"tran":"usb","fstype":null,"label":null,"size":15376318464,"pttype":"dos","model":"Cruzer Blade     ","mountpoint":null,
  "children":[{"name":"sda1","path":"/dev/sda1","type":"part","rm":true,"hotplug":true,"tran":null,"fstype":"vfat","label":"PRINTER","size":15375269888,"pttype":"dos","model":null,"mountpoint":"/"}]},
 {"name":"sdb","path":"/dev/sdb","type":"disk","rm":true,"hotplug":true,"tran":"usb","fstype":null,"label":null,"size":64000000000,"pttype":"gpt","model":"Ultra","mountpoint":null,
  "children":[{"name":"sdb1","path":"/dev/sdb1","type":"part","rm":true,"hotplug":true,"tran":null,"fstype":"exfat","label":"BIG","size":63999000000,"pttype":"gpt","model":null,"mountpoints":[null]}]},
 {"name":"sdc","path":"/dev/sdc","type":"disk","rm":"1","hotplug":"1","tran":"usb","fstype":"vfat","label":"FLOPPY","size":"2000000000","pttype":null,"model":"Stick","mountpoint":null},
 {"name":"sdd","path":"/dev/sdd","type":"disk","rm":false,"hotplug":false,"tran":"sata","fstype":null,"label":null,"size":500000000000,"pttype":"dos","model":"HDD","mountpoint":null,
  "children":[{"name":"sdd1","path":"/dev/sdd1","type":"part","fstype":"vfat","label":"DATA","size":500000000000,"mountpoint":"/data"}]},
 {"name":"loop0","path":"/dev/loop0","type":"loop","rm":false,"hotplug":false,"tran":null,"fstype":"squashfs","size":1000,"mountpoint":"/snap"}
]}`

func TestParseLsblk(t *testing.T) {
	drives, err := parseLsblk([]byte(lsblkSample))
	if err != nil {
		t.Fatal(err)
	}
	if len(drives) != 3 {
		t.Fatalf("expected the 3 USB partitions and no internal disk, got %+v", drives)
	}
	stick, big, floppy := drives[0], drives[1], drives[2]
	if stick.Device != "/dev/sda1" || stick.Root != "/" || stick.Label != "PRINTER" || stick.Table != "dos" ||
		stick.Model != "Cruzer Blade" || stick.Size != 15375269888 {
		t.Errorf("stick: %+v", stick)
	}
	if blocking, _ := stick.problems(0); len(blocking) != 0 {
		t.Errorf("a FAT32 MBR stick must be usable: %v", blocking)
	}
	if big.Device != "/dev/sdb1" || big.Root != "" {
		t.Errorf("big: %+v", big)
	}
	if blocking, _ := big.problems(0); len(blocking) != 2 {
		t.Errorf("exFAT on GPT has two blocking problems, got %v", blocking)
	}
	if floppy.Device != "/dev/sdc" || floppy.FS != "vfat" || floppy.Size != 2000000000 {
		t.Errorf("a stick without a partition table: %+v", floppy)
	}
	if _, err := parseLsblk([]byte("not json")); err == nil {
		t.Error("broken lsblk output must be an error")
	}
}
