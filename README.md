# :crystal_ball: :gem: opalescence :gem: :crystal_ball:

A torrent client written with Python3.6 and asyncio to explore new features in 3.6 and learn more about asyncio, unittests, and more complex system architecture.

Current capabilities:
1. Download a specified .torrent file, piece by piece employing a naive sequential piece requesting strategy without unchoking remote peers.

## Installing Opalescence
clone this repository

`git clone https://github.com/killerbat00/opalescence.git`

install using pip

`pip install -e <path-to-opalescence>`

## using opalescence
download a torrent

`python3 <path-to-opalescence>/opl.py download <.torrent-file> <destination>`

## testing opalescence
`python3 <path-to-opalescence>/opl.py test`

