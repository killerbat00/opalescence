import os

LOGGING = False
DEBUG = True

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(PROJECT_DIR, 'btlib', 'tests', 'data')

TEST_FILE = os.path.join(root, "test_torrents", "torrent_from_dir.torrent")
TEST_OUTPUT_FILE = os.path.join(root, "test_torrents", "op_test_output.torrent")

TEST_TORRENT_DIR = os.path.join(root, "test_torrent_dir")
TEST_TORRENT_DIR_OUTPUT = os.path.join(root, "test_torrents", "op_test_torrent_dir.torrent")

TEST_EXTERNAL_FILE = os.path.join(root, "test_torrents", "qtbittorrent.torrent")
TEST_EXTERNAL_OUTPUT = os.path.join(root, "test_torrents", "op_qtbittorrent.torrent")

STAR_TREK = os.path.join(root, "test_torrents", "star_trek.torrent")

NAME = "opalescence"
VERSION = "0.2"
FULL_NAME = " ".join([NAME, "v"+VERSION])

ANNOUNCE = "www.google.com"
ANNOUNCE_LIST = ["www.google.com", "www.google.com", "www.brianmorrow.net"]
URL_LIST = ["www.google.com", "www.brianmorrow.net", "www.fistingmen.net"]
PRIVATE = False
