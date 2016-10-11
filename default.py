LOGGING = False
DEBUG = True

root = "Y:\Personal\Development\opalescence\\btlib\\tests\\data"

TEST_FILE = "\\".join([root, "test_torrents", "torrent_from_dir.torrent"])
TEST_OUTPUT_FILE = "\\".join([root, "test_torrents", "op_test_output.torrent"])

TEST_TORRENT_DIR = "\\".join([root, "test_torrent_dir"])
TEST_TORRENT_DIR_OUTPUT = "\\".join([root, "test_torrents", "op_test_torrent_dir.torrent"])

TEST_EXTERNAL_FILE = "\\".join([root, "test_torrents", "qtbittorrent.torrent"])
TEST_EXTERNAL_OUTPUT = "\\".join([root, "test_torrents", "op_qtbittorrent.torrent"])

STAR_TREK = "\\".join([root, "test_torrents", "star_trek.torrent"])

NAME = "opalescence"
VERSION = "0.1"
FULL_NAME = " ".join([NAME, "v"+VERSION])

ANNOUNCE = "www.google.com"
ANNOUNCE_LIST = ["www.google.com", "www.google.com", "www.brianmorrow.net"]
URL_LIST = ["www.google.com", "www.brianmorrow.net", "www.fistingmen.net"]
PRIVATE = False
