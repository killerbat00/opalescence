LOGGING = False
DEBUG = True

root = "C:\\Users\\bmorrow\Documents\dev\opalescence\\"

TEST_FILE = root + "btlib\\tests\\data\\test_torrents\\torrent_from_dir.torrent"
TEST_OUTPUT_FILE = root + "btlib\\tests\\data\\test_torrents\\op_test_output.torrent"

TEST_TORRENT_DIR = root + "btlib\\tests\\data\\test_torrent_dir"
TEST_TORRENT_DIR_OUTPUT = root + "btlib\\tests\\data\\test_torrents\\op_test_torrent_dir.torrent"

TEST_EXTERNAL_FILE = root + "btlib\\tests\\data\\test_torrents\\qtbittorrent.torrent"
TEST_EXTERNAL_OUTPUT = root + "btlib\\tests\\data\\test_torrents\\op_qtbittorrent.torrent"

NAME = "opalescence"
VERSION = "0.1"
FULL_NAME = " ".join([NAME, "v"+VERSION])

ANNOUNCE = "www.google.com"
ANNOUNCE_LIST = ["www.google.com", "www.brianmorrow.net"]
URL_LIST = ["www.google.com", "www.brianmorrow.net", "www.fistingmen.net"]
PRIVATE = True
