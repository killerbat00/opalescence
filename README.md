# opalescence

A torrent client written with asyncio and Python 3.6.

Currently, the client employs a naive sequential piece requesting strategy and never unchokes remote peers.


## Installing Opalescence
clone this repository

`git clone https://github.com/killerbat00/opalescence.git`

install using pip

`pip install -e <path-to-opalescence>`

## using opalescence
download a torrent

`python3 <path-to-opalescence>/main.py download <.torrent-file> <destination>`

## testing opalescence
`python3 <path-to-opalescence>/main.py test`

